import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.agents.http_api import app
from src.pipelines import ingest_queue
from src.utils import index_manager, security, storage, siliconflow
from src.utils import session as session_utils
from src.utils.observability import get_metrics
from src.utils.text_extract import ExtractedText


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
        "JWT_SECRET",
        "AUTH_ADMIN_PASSWORD",
        "AUTH_ADMIN_READONLY_PASSWORD",
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
        "JWT_SECRET",
        "AUTH_ADMIN_PASSWORD",
        "AUTH_ADMIN_READONLY_PASSWORD",
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

    slot_update_payload = {"slots": {"target_country": "Canada", "gpa": "3.5"}, "reset_slots": []}
    slot_update_resp = client.patch(f"/v1/session/{query_data['session_id']}/slots", json=slot_update_payload, headers=headers)
    assert slot_update_resp.status_code == 200
    slot_update_data = slot_update_resp.json()
    assert slot_update_data["slots"]["target_country"] == "Canada"

    list_resp = client.get("/v1/session", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert any(item["session_id"] == query_data["session_id"] for item in list_data["sessions"])

    admin_users_resp = client.get("/v1/admin/users", headers=headers)
    assert admin_users_resp.status_code == 200
    admin_users = admin_users_resp.json()
    assert admin_users
    admin_user_id = admin_users[0]["user_id"]

    admin_sessions_resp = client.get("/v1/admin/conversations", headers=headers)
    assert admin_sessions_resp.status_code == 200
    admin_sessions = admin_sessions_resp.json()
    assert any(item["session_id"] == query_data["session_id"] for item in admin_sessions)

    admin_messages_resp = client.get(
        f"/v1/admin/conversations/{admin_user_id}/{query_data['session_id']}/messages",
        headers=headers,
    )
    assert admin_messages_resp.status_code == 200
    admin_messages = admin_messages_resp.json()
    assert admin_messages["session_id"] == query_data["session_id"]

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

    verify_resp = client.post("/v1/admin/sources/visa_requirements/verify", headers=headers)
    assert verify_resp.status_code == 200
    verified_at = verify_resp.json()["verified_at"]

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

    # Streaming SSE (FR-GEN-4 / UX2)
    stream_headers = dict(headers)
    stream_headers["Accept"] = "text/event-stream"
    with client.stream("POST", "/v1/query?stream=true", json=query_payload, headers=stream_headers) as stream_resp:
        assert stream_resp.status_code == 200
        events = []
        for line in stream_resp.iter_lines():
            if line.startswith("event:"):
                events.append(line.replace("event:", "").strip())
            if "completed" in events and len(events) >= 2:
                break
        assert "citations" in events
        assert "completed" in events

    # Early-abort stream (Stop generating): server should tolerate disconnect without error
    with client.stream("POST", "/v1/query?stream=true", json=query_payload, headers=stream_headers) as stream_resp2:
        assert stream_resp2.status_code == 200
        it = stream_resp2.iter_lines()
        for _ in range(3):
            next(it, "")
        # Exit context early -> client disconnects

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

    history_resp = client.get("/v1/metrics/history", headers=headers)
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    assert history_data["entries"]
    latest = history_data["entries"][-1]
    assert "timestamp" in latest
    assert "snapshot" in latest

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

    eval_payload = {
        "top_k": 3,
        "return_details": True,
        "cases": [{"query": "student visa requirements", "relevant_doc_ids": ["visa_requirements"]}],
    }
    eval_resp = client.post("/v1/admin/eval/retrieval", json=eval_payload, headers=headers)
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["total_cases"] == 1
    assert eval_data["top_k"] == 3
    assert eval_data["cases"]

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


def test_image_upload_ingest_query_with_ocr_stub(temp_storage, monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "secret")

    def fake_extract_text(*, content: bytes, mime_type: str, filename: str) -> ExtractedText:
        assert mime_type.startswith("image/")
        return ExtractedText(
            text="OCR result: passport and bank statements are required.",
            metadata={"ocr_engine": "stub", "ocr_pages": [{"page": 1, "confidence": 0.95}]},
        )

    monkeypatch.setattr(ingest_queue, "extract_text_from_bytes", fake_extract_text)

    client = TestClient(app)
    headers = {"X-API-Key": "secret"}

    upload_resp = client.post(
        "/v1/upload",
        headers=headers,
        files={"file": ("sample.png", b"fake-image-bytes", "image/png")},
    )
    assert upload_resp.status_code == 200
    upload_id = upload_resp.json()["upload_id"]

    ingest_resp = client.post("/v1/ingest-upload", json={"upload_id": upload_id}, headers=headers)
    assert ingest_resp.status_code == 200

    query_resp = client.post(
        "/v1/query",
        json={"question": "Which documents are required?", "language": "en"},
        headers=headers,
    )
    assert query_resp.status_code == 200
    query_data = query_resp.json()
    assert query_data["citations"]
    assert "passport" in query_data["citations"][0]["snippet"].lower()


def test_audio_upload_ingest_query_with_stt_stub(temp_storage, monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "secret")

    def fake_extract_text(*, content: bytes, mime_type: str, filename: str) -> ExtractedText:
        assert mime_type.startswith("audio/")
        return ExtractedText(
            text="Transcript: visa interview checklist and required documents.",
            metadata={"stt_engine": "stub", "stt_segments": [{"start": 0.0, "end": 1.2, "text": "visa interview checklist"}]},
        )

    monkeypatch.setattr(ingest_queue, "extract_text_from_bytes", fake_extract_text)

    client = TestClient(app)
    headers = {"X-API-Key": "secret"}

    upload_resp = client.post(
        "/v1/upload",
        headers=headers,
        files={"file": ("sample.mp3", b"fake-audio-bytes", "audio/mpeg")},
    )
    assert upload_resp.status_code == 200
    upload_id = upload_resp.json()["upload_id"]

    ingest_resp = client.post("/v1/ingest-upload", json={"upload_id": upload_id}, headers=headers)
    assert ingest_resp.status_code == 200

    query_resp = client.post(
        "/v1/query",
        json={"question": "What is mentioned in the audio?", "language": "en"},
        headers=headers,
    )
    assert query_resp.status_code == 200
    query_data = query_resp.json()
    assert query_data["citations"]
    assert "visa" in query_data["citations"][0]["snippet"].lower()


def test_http_admin_readonly_blocks_writes(temp_storage, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("AUTH_ADMIN_READONLY_PASSWORD", "readonly")

    client = TestClient(app)
    login_resp = client.post("/v1/auth/login", json={"username": "readonly-admin", "password": "readonly"})
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert login_data["role"] == "admin_readonly"

    headers = {"Authorization": f"Bearer {login_data['access_token']}"}
    read_resp = client.get("/v1/admin/config", headers=headers)
    assert read_resp.status_code == 200

    update_payload = {"alpha": 0.6, "top_k": 8, "k_cite": 2}
    write_resp = client.post("/v1/admin/retrieval", json=update_payload, headers=headers)
    assert write_resp.status_code == 403


def test_http_reran_rerank_endpoint(temp_storage, monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "secret")

    async def fake_rerank_async(query, documents, *, model=None, trace_id=None, language=None):
        assert query == "visa"
        assert documents == ["doc-a", "doc-b", "doc-c"]
        return [(1, 0.9), (0, 0.2), (2, 0.1)]

    monkeypatch.setattr(siliconflow, "rerank_async", fake_rerank_async)

    client = TestClient(app)
    headers = {"X-API-Key": "secret"}
    payload = {
        "query": "visa",
        "language": "en",
        "documents": [
            {"text": "doc-a"},
            {"text": "doc-b"},
            {"text": "doc-c"},
        ],
    }

    resp = client.post("/v1/reran", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "visa"
    assert data["trace_id"]
    assert [item["index"] for item in data["results"]] == [1, 0, 2]
    assert data["results"][0]["document"]["text"] == "doc-b"

    alias_resp = client.post("/reran", json=payload, headers=headers)
    assert alias_resp.status_code == 200
    alias_data = alias_resp.json()
    assert [item["index"] for item in alias_data["results"]] == [1, 0, 2]
