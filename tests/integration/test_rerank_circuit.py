
import asyncio

import httpx
import pytest

from src.agents.rag_agent import answer_query
from src.schemas.models import QueryRequest
from src.utils import siliconflow, index_manager, session as session_utils, storage
from src.utils.chunking import simple_paragraph_chunk
from src.utils.observability import get_metrics


@pytest.mark.asyncio
async def test_answer_query_rerank_circuit_open(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    snapshots = tmp_path / "snapshots"
    manifest = processed / "manifest.json"
    monkeypatch.setattr(storage, "DATA_RAW", raw)
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed)
    monkeypatch.setattr(storage, "DATA_SNAPSHOTS", snapshots)
    monkeypatch.setattr(storage, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(index_manager, "DATA_PROCESSED", processed)
    monkeypatch.setattr(index_manager, "_INDEX_MANAGER", index_manager.IndexManager())
    monkeypatch.setattr(session_utils, "_SESSION_STORE", session_utils.SessionStore(ttl_seconds=3600))
    storage.ensure_dirs()

    content = (
        "Student visa application fees and processing time vary by country.\n\n"
        "Required documents include passport, bank statements, and admission letter."
    )
    chunks = simple_paragraph_chunk(content, doc_id="d1", max_chars=200)
    storage.save_chunks("d1", chunks)

    siliconflow.reset_rerank_circuit()
    get_metrics().reset()
    monkeypatch.setenv("SILICONFLOW_API_KEY", "dummy")
    monkeypatch.setenv("SILICONFLOW_RERANK_CB_FAILURE_THRESHOLD", "1")
    monkeypatch.setenv("SILICONFLOW_RERANK_CB_RESET_SECONDS", "60")
    monkeypatch.setenv("SILICONFLOW_RERANK_MAX_ATTEMPTS", "1")

    async def fake_chat(*args, **kwargs):
        return "stub answer"

    monkeypatch.setattr("src.agents.rag_agent.chat", fake_chat)

    request = httpx.Request("POST", "https://api.siliconflow.cn/v1/rerank")

    class FailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ReadTimeout("timeout", request=request)

    monkeypatch.setattr(siliconflow.httpx, "AsyncClient", lambda *args, **kwargs: FailClient())

    query = QueryRequest(question="documents required", language="en", top_k=4, k_cite=2)
    first_response = await answer_query(query)
    assert first_response.citations

    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_circuit::opened"] == 1.0
    assert counters["rerank_fallback::error"] == 1.0
    assert counters["rerank_language_fallback::en"] == 1.0

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("circuit open should bypass HTTP client")

    monkeypatch.setattr(siliconflow.httpx, "AsyncClient", UnexpectedClient)

    second_response = await answer_query(query)
    assert second_response.citations

    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_circuit::open_skip"] == 1.0
    assert counters["rerank_fallback::circuit_open"] == 1.0
    assert counters["rerank_language_fallback::en"] >= 2.0

    siliconflow.reset_rerank_circuit()
