import asyncio

import pytest

from src.agents.rag_agent import answer_query
from src.schemas.models import Document, QueryRequest
from src.utils import index_manager, session as session_utils, storage
from src.utils.chunking import simple_paragraph_chunk


@pytest.mark.smoke
def test_answer_query_offline(tmp_path, monkeypatch):
    # Prepare isolated storage for the test corpus
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
    storage.upsert_document(Document(doc_id="d1", source_name="d1"))
    storage.save_chunks("d1", chunks)

    # Ensure no external call if no key
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)

    req = QueryRequest(question="What documents are required for student visa?", language="en", top_k=4, k_cite=2)

    async def run():
        resp = await answer_query(req, user_id="test-user")
        assert resp.answer, "should get an answer string"
        assert resp.citations, "should include citations"
        assert resp.diagnostics is not None
        assert resp.diagnostics.retrieval_ms >= 0
        assert resp.diagnostics.end_to_end_ms >= resp.diagnostics.retrieval_ms
        first_citation = resp.citations[0]
        assert first_citation.start_char is not None
        assert first_citation.end_char is not None
        assert resp.session_id
        assert isinstance(resp.slots, dict)
        assert "target_country" in resp.missing_slots
        assert resp.slot_prompts.get("target_country")
        assert not resp.slot_suggestions
        for citation in resp.citations:
            chunk = storage.load_chunk_by_id(citation.chunk_id)
            assert chunk is not None
            assert chunk.start_idx == citation.start_char
            assert chunk.end_idx == citation.end_char
            assert citation.highlights

        zh_req = QueryRequest(
            question="申请英国留学需要准备哪些材料？",
            language="zh",
            top_k=4,
            k_cite=2,
        )
        zh_resp = await answer_query(zh_req, user_id="test-user")
        assert zh_resp.missing_slots
        assert zh_resp.slot_prompts.get("target_country", "").startswith("你计划")
        assert not zh_resp.slot_suggestions

        follow_up = QueryRequest(
            question="What documents are required for student visa?",
            language="en",
            top_k=4,
            k_cite=2,
            session_id=resp.session_id,
            slots={"target_country": "United Kingdom", "student_name": "Test Student"},
            temperature=0.1,
            top_p=0.7,
            max_tokens=150,
            stop=["STOP"],
            model="test-model",
            explain_like_new=True,
        )
        resp_again = await answer_query(follow_up, user_id="test-user")
        assert resp_again.session_id == resp.session_id
        assert resp_again.slots["target_country"] == "United Kingdom"
        assert "target_country" not in resp_again.missing_slots
        assert not resp_again.slot_suggestions
        assert resp_again.slot_errors == {}
        assert resp_again.diagnostics is not None
        assert resp_again.diagnostics.low_confidence is False

        invalid_req = QueryRequest(
            question="Do I qualify?",
            language="en",
            session_id=resp_again.session_id,
            slots={"ielts": -1},
        )
        invalid_resp = await answer_query(invalid_req, user_id="test-user")
        assert invalid_resp.slot_errors.get("ielts") == "must be ≥ 0.0"

    asyncio.run(run())
