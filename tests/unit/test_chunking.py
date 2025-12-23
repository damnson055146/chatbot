import pytest

from src.utils.chunking import simple_paragraph_chunk


@pytest.mark.smoke
def test_simple_paragraph_chunk_basic():
    text = "Para one.\n\nPara two is a bit longer to ensure splitting works properly across multiple paragraphs."
    chunks = simple_paragraph_chunk(text, doc_id="doc1", max_chars=20, overlap=5)
    assert chunks, "should create chunks"
    # Chunks should belong to the same document and keep order
    assert all(c.doc_id == "doc1" for c in chunks)
    assert chunks[0].text.startswith("Para one")
    assert all("start_idx" in c.metadata and "end_idx" in c.metadata for c in chunks)

