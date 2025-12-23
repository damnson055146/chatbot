
import pytest

from src.utils import siliconflow
from src.utils.index import Retrieved
from src.utils.observability import get_metrics
from src.utils.rerank import get_reranker


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    get_metrics().reset()
    siliconflow.reset_rerank_circuit()
    monkeypatch.delenv("SILICONFLOW_RERANK_MODEL", raising=False)
    yield
    get_metrics().reset()
    siliconflow.reset_rerank_circuit()
    monkeypatch.delenv("SILICONFLOW_RERANK_MODEL", raising=False)


@pytest.mark.asyncio
async def test_siliconflow_reranker_uses_scores(monkeypatch):
    documents = [
        Retrieved(chunk_id="a", text="apple guidance", score=0.1, meta={}),
        Retrieved(chunk_id="b", text="banana scholarship", score=0.2, meta={}),
        Retrieved(chunk_id="c", text="visa information", score=0.3, meta={}),
    ]

    async def fake_rerank_async(query, docs, *, model=None, trace_id=None, language=None):  # pragma: no cover - simple override
        assert query == "fruit"
        assert docs == [item.text for item in documents]
        return [(2, 0.95), (0, 0.5), (1, 0.1)]

    monkeypatch.setattr(siliconflow, "rerank_async", fake_rerank_async)
    reranker = get_reranker()
    ordered = await reranker.rerank("fruit", documents, language="en")
    assert [item.chunk_id for item in ordered] == ["c", "a", "b"]

    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_model::default"] == 1.0
    assert counters["rerank_language::en"] == 1.0


@pytest.mark.asyncio
async def test_siliconflow_reranker_graceful_when_no_scores(monkeypatch):
    documents = [
        Retrieved(chunk_id="a", text="apple", score=0.1, meta={}),
        Retrieved(chunk_id="b", text="banana", score=0.2, meta={}),
    ]

    async def empty_rerank_async(query, docs, *, model=None, trace_id=None, language=None):
        return []

    monkeypatch.setattr(siliconflow, "rerank_async", empty_rerank_async)
    reranker = get_reranker()
    ordered = await reranker.rerank("fruit", documents, language="en")
    assert ordered == documents

    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_model::default"] == 1.0
    assert counters["rerank_language::en"] == 1.0
    assert counters["rerank_language_fallback::en"] == 1.0
    assert counters["rerank_fallback::empty_scores"] == 1.0
