from __future__ import annotations

import pytest

from src.agents import rag_agent
from src.schemas.models import Document, QueryRequest
from src.utils import storage
from src.utils.conversation_store import ConversationStore
from src.utils.index import Retrieved
from src.utils.text_extract import ExtractedText


def _prepare_uploads(tmp_path, monkeypatch) -> None:
    uploads = tmp_path / "uploads"
    processed = tmp_path / "processed"
    uploads.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(storage, "UPLOADS_DIR", uploads)
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed)
    storage.ensure_dirs()
    monkeypatch.setattr(rag_agent, "UPLOADS_DIR", uploads)


def _stub_rag_dependencies(monkeypatch, captured_query):
    class StubIndexManager:
        alpha = 0.5

        def query(self, question: str, top_k: int = 8):
            captured_query["value"] = question
            return [
                Retrieved(
                    chunk_id="doc1-0",
                    text="Attachment mentions passport requirements.",
                    score=0.9,
                    meta={"doc_id": "doc1", "start_idx": 0, "end_idx": 34},
                )
            ]

    class StubReranker:
        async def rerank(self, question, items, trace_id: str, language: str):
            return items

    documents = {"doc1": Document(doc_id="doc1", source_name="Upload Notes", language="en")}

    async def fake_chat(prompt: str, *, system_message: str, **_: object) -> str:
        return "Final answer"

    monkeypatch.setattr(rag_agent, "get_index_manager", lambda: StubIndexManager())
    monkeypatch.setattr(rag_agent, "get_reranker", lambda: StubReranker())
    monkeypatch.setattr(rag_agent, "get_doc_lookup", lambda: documents)
    monkeypatch.setattr(rag_agent, "chat", fake_chat)


@pytest.mark.asyncio
async def test_answer_query_merges_attachment_text(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_uploads(tmp_path, monkeypatch)
    store = ConversationStore()
    monkeypatch.setattr(rag_agent, "get_conversation_store", lambda: store)

    record = storage.save_upload_file(
        filename="note.txt",
        content=b"placeholder",
        mime_type="text/plain",
    )

    monkeypatch.setattr(
        rag_agent,
        "extract_text_from_bytes",
        lambda **_: ExtractedText(text="Attachment summary", metadata={}),
    )

    captured_query = {}
    _stub_rag_dependencies(monkeypatch, captured_query)

    req = QueryRequest(
        question="Base question",
        language="en",
        attachments=[record.upload_id],
    )
    await rag_agent.answer_query(req, user_id="test-user")

    assert "Attachment summary" in captured_query.get("value", "")


@pytest.mark.asyncio
async def test_answer_query_uses_multimodal_for_images(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _prepare_uploads(tmp_path, monkeypatch)
    store = ConversationStore()
    monkeypatch.setattr(rag_agent, "get_conversation_store", lambda: store)

    record = storage.save_upload_file(
        filename="image.png",
        content=b"fake-image-bytes",
        mime_type="image/png",
    )

    monkeypatch.setattr(
        rag_agent,
        "extract_text_from_bytes",
        lambda **_: ExtractedText(text="Image text", metadata={}),
    )

    captured_query = {}
    _stub_rag_dependencies(monkeypatch, captured_query)

    calls = {"multimodal": False, "chat": False}

    async def fake_multimodal(prompt: str, *, system_message: str, image_data_urls, **_: object) -> str:
        calls["multimodal"] = True
        assert image_data_urls
        return "Answer"

    async def fake_chat(prompt: str, *, system_message: str, **_: object) -> str:
        calls["chat"] = True
        return "Answer"

    monkeypatch.setattr(rag_agent, "chat_multimodal", fake_multimodal)
    monkeypatch.setattr(rag_agent, "chat", fake_chat)

    req = QueryRequest(
        question="Describe the image",
        language="en",
        attachments=[record.upload_id],
    )
    await rag_agent.answer_query(req, user_id="test-user")

    assert calls["multimodal"] is True
    assert calls["chat"] is False
