import pytest

from src.utils.index import HybridIndex


@pytest.mark.smoke
def test_hybrid_index_query():
    chunks = [
        ("c1", "visa application requirements and fees", {"doc_id": "d1"}),
        ("c2", "scholarship deadlines and eligibility", {"doc_id": "d2"}),
        ("c3", "admissions GPA requirements for masters", {"doc_id": "d3"}),
    ]
    idx = HybridIndex(chunks)
    res = idx.query("What are the visa requirements?", top_k=2)
    assert len(res) == 2
    assert any("visa" in r.text for r in res)

