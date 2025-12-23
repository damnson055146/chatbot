from __future__ import annotations

from contextlib import contextmanager

import pytest

from src.agents import rag_agent
from src.schemas.models import Document, QueryRequest
from src.utils.index import Retrieved
from src.utils.session import SessionStore


class _FakeSpan:
    def __init__(self, name: str, attributes: dict | None) -> None:
        self.name = name
        self.attributes = dict(attributes or {})
        self.set_attributes: dict[str, object] = {}

    def set_attribute(self, key: str, value: object) -> None:
        self.set_attributes[key] = value

    def record_exception(self, exc: Exception) -> None:  # pragma: no cover - defensive
        self.set_attributes["exception"] = str(exc)


@pytest.mark.asyncio
async def test_answer_query_emits_tracing_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    span_records: list[_FakeSpan] = []

    @contextmanager
    def fake_start_span(name: str, attributes: dict | None = None):
        span = _FakeSpan(name, attributes)
        span_records.append(span)
        yield span

    monkeypatch.setattr(rag_agent, "start_span", fake_start_span)

    session_store = SessionStore(ttl_seconds=3600)
    monkeypatch.setattr(rag_agent, "get_session_store", lambda: session_store)

    retrieved_items = [
        Retrieved(
            chunk_id="doc1-0",
            text="Visa processing times vary by country.",
            score=0.9,
            meta={"doc_id": "doc1", "start_idx": 0, "end_idx": 42},
        ),
        Retrieved(
            chunk_id="doc2-0",
            text="Applicants need bank statements and passport.",
            score=0.85,
            meta={"doc_id": "doc2", "start_idx": 5, "end_idx": 55},
        ),
    ]

    class StubIndexManager:
        alpha = 0.5

        def query(self, question: str, top_k: int = 8):
            return retrieved_items[:top_k]

    monkeypatch.setattr(rag_agent, "get_index_manager", lambda: StubIndexManager())

    documents = {
        "doc1": Document(doc_id="doc1", source_name="Visa Guide", language="en"),
        "doc2": Document(doc_id="doc2", source_name="Requirements", language="en"),
    }
    monkeypatch.setattr(rag_agent, "get_doc_lookup", lambda: documents)

    class StubReranker:
        async def rerank(self, question, items, trace_id: str, language: str):
            return items

    monkeypatch.setattr(rag_agent, "get_reranker", lambda: StubReranker())

    async def fake_chat(prompt: str, *, system_message: str, **_: object) -> str:
        assert "Slots:" in prompt
        assert system_message
        return "Final answer"

    monkeypatch.setattr(rag_agent, "chat", fake_chat)

    req = QueryRequest(
        question="What documents are needed for a student visa?",
        language="en",
        top_k=2,
        k_cite=2,
        slots={"target_country": "Canada"},
        stop=["STOP"],
        explain_like_new=True,
    )

    response = await rag_agent.answer_query(req)

    span_names = [span.name for span in span_records]
    assert "rag.retrieval" in span_names
    assert "rag.rerank" in span_names
    assert "rag.generation" in span_names

    retrieval_span = next(span for span in span_records if span.name == "rag.retrieval")
    assert retrieval_span.attributes["trace_id"] == response.trace_id
    assert retrieval_span.attributes["retrieval.top_k"] == req.top_k
    assert retrieval_span.set_attributes["retrieval.result_count"] == len(retrieved_items)

    rerank_span = next(span for span in span_records if span.name == "rag.rerank")
    assert rerank_span.attributes["session_id"] == response.session_id
    assert rerank_span.set_attributes["rerank.result_count"] == len(retrieved_items)

    generation_span = next(span for span in span_records if span.name == "rag.generation")
    assert generation_span.attributes["generation.stop_count"] == 1
    assert generation_span.set_attributes["generation.citation_count"] == len(response.citations)
    assert generation_span.set_attributes["generation.missing_slots"] == len(response.missing_slots)
