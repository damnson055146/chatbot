from __future__ import annotations

from datetime import UTC, datetime
import time
from typing import List, Optional

from src.schemas.models import IndexHealth
from src.utils.index import HybridIndex, Retrieved
from src.utils.faiss_index import FaissIndex, faiss_available
from src.utils.logging import get_logger
from src.utils.storage import (
    DATA_PROCESSED,
    ensure_dirs,
    load_chunks,
    load_manifest,
    load_retrieval_settings,
    append_job_history,
)

log = get_logger(__name__)


class IndexManager:
    def __init__(self, alpha: float = 0.5, default_top_k: int = 8, default_k_cite: int = 2) -> None:
        self.alpha = alpha
        self.default_top_k = default_top_k
        self.default_k_cite = default_k_cite
        self._index: Optional[HybridIndex | FaissIndex] = None
        self.index_backend: str = "hybrid"
        self.last_build_at: Optional[datetime] = None
        self.document_count: int = 0
        self.chunk_count: int = 0
        self.errors: List[str] = []

    def configure(self, *, alpha: Optional[float] = None, top_k: Optional[int] = None, k_cite: Optional[int] = None) -> None:
        if alpha is not None:
            self.alpha = alpha
        if top_k is not None:
            self.default_top_k = int(top_k)
        if k_cite is not None:
            self.default_k_cite = int(k_cite)

    def rebuild(self) -> None:
        ensure_dirs()
        self.errors.clear()
        start_time = time.perf_counter()
        chunk_records = []
        doc_ids = set()

        try:
            manifest_docs = load_manifest()
            if manifest_docs:
                for doc in manifest_docs:
                    doc_ids.add(doc.doc_id)
                    for chunk in load_chunks(doc.doc_id):
                        chunk_records.append((chunk.chunk_id, chunk.text, chunk.metadata))
            else:
                for path in DATA_PROCESSED.glob("*.chunks.json"):
                    doc_id = path.name.replace(".chunks.json", "")
                    doc_ids.add(doc_id)
                    for chunk in load_chunks(doc_id):
                        chunk_records.append((chunk.chunk_id, chunk.text, chunk.metadata))

            if chunk_records:
                if faiss_available():
                    self._index = FaissIndex(chunk_records)
                    self.index_backend = "faiss"
                else:
                    self._index = HybridIndex(chunk_records)
                    self.index_backend = "hybrid"
            else:
                self._index = None
                self.index_backend = "hybrid"

            self.chunk_count = len(chunk_records)
            self.document_count = len(manifest_docs) if manifest_docs else len(doc_ids)
            self.last_build_at = datetime.now(UTC)
            duration_ms = (time.perf_counter() - start_time) * 1000
            log.info(
                "index_rebuilt",
                document_count=self.document_count,
                chunk_count=self.chunk_count,
                backend=self.index_backend,
            )
            append_job_history(
                {
                    "job_type": "index_rebuild",
                    "status": "succeeded",
                    "document_count": self.document_count,
                    "chunk_count": self.chunk_count,
                    "backend": self.index_backend,
                    "duration_ms": duration_ms,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            self._index = None
            self.errors.append(str(exc))
            log.error("index_rebuild_failed", error=str(exc))
            raise

    def query(self, query: str, *, top_k: int = 8, alpha: Optional[float] = None) -> List[Retrieved]:
        if self._index is None:
            self.rebuild()
        if self._index is None:
            return []
        limit = top_k if top_k is not None else self.default_top_k
        if isinstance(self._index, HybridIndex):
            weight = alpha if alpha is not None else self.alpha
            return self._index.query(query, top_k=limit, alpha=weight)
        return self._index.query(query, top_k=limit)

    def health(self) -> IndexHealth:
        return IndexHealth(
            document_count=self.document_count,
            chunk_count=self.chunk_count,
            last_build_at=self.last_build_at,
            errors=list(self.errors),
        )

    def summary(self) -> dict:
        return {
            "alpha": self.alpha,
            "top_k": self.default_top_k,
            "k_cite": self.default_k_cite,
            "document_count": self.document_count,
            "chunk_count": self.chunk_count,
            "last_build_at": self.last_build_at,
            "backend": self.index_backend,
        }


_INDEX_MANAGER = IndexManager()
_SETTINGS = load_retrieval_settings()
if _SETTINGS:
    _INDEX_MANAGER.configure(
        alpha=_SETTINGS.get("alpha"),
        top_k=_SETTINGS.get("top_k"),
        k_cite=_SETTINGS.get("k_cite"),
    )


def get_index_manager() -> IndexManager:
    return _INDEX_MANAGER

