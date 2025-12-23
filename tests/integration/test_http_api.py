import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.agents.http_api import app
from src.utils import index_manager, security, storage
from src.utils import session as session_utils
from src.utils.observability import get_metrics


@pytest.fixture
def temp_storage(monkeypatch, tmp_path):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    snapshots = tmp_path / "snapshots"
    manifest_path = processed / "manifest.json"

    monkeypatch.setattr(storage, "DATA_RAW", raw)
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed)
    monkeypatch.setattr(storage, "DATA_SNAPSHOTS", snapshots)
    monkeypatch.setattr(storage, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(index_manager, "DATA_PROCESSED", processed)
    monkeypatch.setattr(index_manager, "_INDEX_MANAGER", index_manager.IndexManager())
    monkeypatch.setattr(session_utils, "_SESSION_STORE", session_utils.SessionStore(ttl_seconds=3600))
    monkeypatch.setattr(security, "_rate_limiter", None)
    storage.ensure_dirs()
    get_metrics().reset()

    return processed


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for key in [
        "SILICONFLOW_API_KEY",
        "API_AUTH_TOKEN",
        "API_RATE_LIMIT",
        "API_RATE_WINDOW",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(security, "_rate_limiter", None)
    get_metrics().reset()
    yield
    for key in [
        "SILICONFLOW_API_KEY",
        "API_AUTH_TOKEN",
        "API_RATE_LIMIT",
        "API_RATE_WINDOW",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(security, "_rate_limiter", None)
    get_metrics().reset()


@pytest.mark.smoke
def test_http_ingest_and_query_with_auth(temp_storage, monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "secret")
    monkeypatch.setenv("API_RATE_LIMIT", "20")
    monkeypatch.setenv("API_RATE_WINDOW", "60")

    client = TestClient(app)
    headers = {"X-API-Key": "secret"}

    ingest_payload = {
        "source_name": "visa_requirements",
        "content": "Student visa requires passport and financial proof.",
        "language": "en",
        "domain": "visa",
    }

    ingest_resp = client.post("/v1/ingest", json=ingest_payload, headers=headers)
    assert ingest_resp.status_code == 200
    assert "X-Request-ID" in ingest_resp.headers

    query_payload = {
        "question": "What is needed for student visa?",
        "language": "en",
        "temperature": 0.3,
        "top_p": 0.8,
        "max_tokens": 200,
        "stop": ["STOP"],
        "model": "test-model",
    }
    query_resp = client.post("/v1/query", json=query_payload, headers=headers)
    assert query_resp.status_code == 200
    assert "X-Request-ID" in query_resp.headers

    query_data = query_resp.json()
    assert query_data["session_id"]
    assert isinstance(query_data["slots"], dict)
    assert "target_country" in query_data["missing_slots"]
    assert query_data["citations"][0]["start_char"] is not None
    assert query_data["citations"][0]["end_char"] is not None
    assert query_data["citations"][0]["highlights"]
    assert query_data["slot_errors"] == {}
    diagnostics_block = query_data.get("diagnostics")
    assert diagnostics_block is not None
    assert diagnostics_block["retrieval_ms"] >= 0
    assert diagnostics_block["end_to_end_ms"] >= diagnostics_block["retrieval_ms"]
    assert diagnostics_block.get("low_confidence") in {True, False}
    chunk_id = query_data["citations"][0]["chunk_id"]

    chunk_resp = client.get(f"/v1/chunks/{chunk_id}", headers=headers)
    assert chunk_resp.status_code == 200
    chunk_data = chunk_resp.json()
    assert chunk_data["chunk"]["chunk_id"] == chunk_id
    assert chunk_data["chunk"]["text"]
    assert chunk_data["chunk"]["metadata"]["doc_id"] == query_data["citations"][0]["doc_id"]
    assert chunk_data["chunk"]["highlights"]

    slots_resp = client.get("/v1/slots", headers=headers)
    assert slots_resp.status_code == 200
    slots_data = slots_resp.json()
    assert any(slot["name"] == "target_country" for slot in slots_data["slots"])
    zh_resp = client.get("/v1/slots", headers={"X-API-Key": "secret", "Accept-Language": "zh"})
    assert zh_resp.status_code == 200
    zh_data = zh_resp.json()
    target_entry = next(slot for slot in zh_data["slots"] if slot["name"] == "target_country")
    assert target_entry["prompt"].startswith("你计划")

    session_resp = client.get(f"/v1/session/{query_data['session_id']}", headers=headers)
    assert session_resp.status_code == 200
    session_data = session_resp.json()
    assert session_data["session_id"] == query_data["session_id"]

    list_resp = client.get("/v1/session", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert any(item["session_id"] == query_data["session_id"] for item in list_data["sessions"])

    delete_resp = client.delete(f"/v1/session/{query_data['session_id']}", headers=headers)
    assert delete_resp.status_code == 204

    source_upsert = {
        "doc_id": "visa_requirements",
        "source_name": "visa_requirements",
        "language": "en",
        "domain": "visa",
        "freshness": "2025-01-01",
        "url": "https://example.edu/visa",
        "tags": ["policy"],
        "description": "Visa requirements summary",
    }
    upsert_resp = client.post("/v1/admin/sources", json=source_upsert, headers=headers)
    assert upsert_resp.status_code == 200
    upsert_data = upsert_resp.json()
    assert upsert_data["source"]["doc_id"] == "visa_requirements"

    sources_resp = client.get("/v1/admin/sources", headers=headers)
    assert sources_resp.status_code == 200
    sources_data = sources_resp.json()
    assert any(item["doc_id"] == "visa_requirements" for item in sources_data)

    delete_source_resp = client.delete("/v1/admin/sources/visa_requirements", headers=headers)
    assert delete_source_resp.status_code == 200
    assert delete_source_resp.json()["deleted"] is True

    stop_list_payload = {"items": ["forbidden term", "blacklisted phrase"]}
    stop_update_resp = client.post("/v1/admin/stop-list", json=stop_list_payload, headers=headers)
    assert stop_update_resp.status_code == 200
    stop_data = stop_update_resp.json()
    assert stop_data["items"] == stop_list_payload["items"]

    stop_list_resp = client.get("/v1/admin/stop-list", headers=headers)
    assert stop_list_resp.status_code == 200
    assert stop_list_resp.json()["items"] == stop_list_payload["items"]

    missing_source_resp = client.delete("/v1/admin/sources/visa_requirements", headers=headers)
    assert missing_source_resp.status_code == 404

    jobs_resp = client.get("/v1/admin/jobs", headers=headers)
    assert jobs_resp.status_code == 200
    jobs_data = jobs_resp.json()
    assert jobs_data["jobs"]

    template_payload = {
        "template_id": "eligibility_summary",
        "name": "Eligibility Summary",
        "content": "Summarize eligibility requirements with citations.",
        "language": "en",
        "category": "eligibility",
    }
    template_upsert = client.post("/v1/admin/templates", json=template_payload, headers=headers)
    assert template_upsert.status_code == 200
    template_list = client.get("/v1/admin/templates", headers=headers)
    assert template_list.status_code == 200
    assert any(item["template_id"] == "eligibility_summary" for item in template_list.json())
    template_delete = client.delete("/v1/admin/templates/eligibility_summary", headers=headers)
    assert template_delete.status_code == 200
    missing_template = client.delete("/v1/admin/templates/eligibility_summary", headers=headers)
    assert missing_template.status_code == 404

    prompt_payload = {
        "prompt_id": "study_abroad_system",
        "name": "Study Abroad System Prompt",
        "content": "You are a study abroad assistant.",
        "language": "en",
        "description": "Default system prompt",
    }
    prompt_upsert = client.post("/v1/admin/prompts", json=prompt_payload, headers=headers)
    assert prompt_upsert.status_code == 200
    prompt_list = client.get("/v1/admin/prompts", headers=headers)
    assert prompt_list.status_code == 200
    assert any(item["prompt_id"] == "study_abroad_system" for item in prompt_list.json())
    activate_resp = client.post("/v1/admin/prompts/study_abroad_system/activate", headers=headers)
    assert activate_resp.status_code == 200
    active_data = activate_resp.json()
    assert active_data["prompt"]["is_active"] is True
    prompt_delete = client.delete("/v1/admin/prompts/study_abroad_system", headers=headers)
    assert prompt_delete.status_code == 200
    missing_prompt = client.delete("/v1/admin/prompts/study_abroad_system", headers=headers)
    assert missing_prompt.status_code == 404

    missing_resp = client.get(f"/v1/session/{query_data['session_id']}", headers=headers)
    assert missing_resp.status_code == 404

    status_resp = client.get("/v1/status", headers=headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["categories"]

    metrics_resp = client.get("/v1/metrics", headers=headers)
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    query_block = metrics_data.get("/v1/query", {})
    assert query_block.get("count", 0) >= 1
    phase_block = metrics_data.get("phases", {})
    assert phase_block.get("retrieval", {}).get("p95_latency_ms") is not None
    diagnostics_block = metrics_data.get("diagnostics", {})
    assert diagnostics_block.get("empty_retrievals") >= 0
    assert diagnostics_block.get("low_confidence_answers") >= 0
    status_block = metrics_data.get("status", {})
    assert "latency" in status_block and "quality" in status_block

    admin_resp = client.get("/v1/admin/config", headers=headers)
    assert admin_resp.status_code == 200
    admin_data = admin_resp.json()
    assert admin_data["sources"]
    assert admin_data["slots"]
    assert admin_data["retrieval"]["alpha"] == 0.5

    update_payload = {"alpha": 0.7, "top_k": 10, "k_cite": 3}
    update_resp = client.post("/v1/admin/retrieval", json=update_payload, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.json()["alpha"] == 0.7
    updated_config = client.get("/v1/admin/config", headers=headers).json()
    assert updated_config["retrieval"]["alpha"] == 0.7

    rate_limit_triggered = False
    for _ in range(25):
        follow_up = client.post("/v1/query", json=query_payload, headers=headers)
        if follow_up.status_code == 429:
            rate_limit_triggered = True
            break
    assert rate_limit_triggered


@pytest.mark.smoke
def test_http_auth_rejection(temp_storage, monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "secret")
    client = TestClient(app)
    ingest_payload = {
        "source_name": "visa_requirements",
        "content": "Student visa requires passport.",
    }
    resp = client.post("/v1/ingest", json=ingest_payload)
    assert resp.status_code == 401
