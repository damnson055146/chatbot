from __future__ import annotations

from typing import List, Tuple

from src.utils.index import DenseEmbedder, Retrieved, SiliconFlowEmbedder
from src.utils.logging import get_logger

try:  # pragma: no cover - exercised when faiss is available
    import faiss
    import numpy as np

    _FAISS_AVAILABLE = True
except Exception:  # pragma: no cover - fallback when faiss is missing
    faiss = None
    np = None
    _FAISS_AVAILABLE = False


def faiss_available() -> bool:
    """Return True when faiss is importable."""

    return _FAISS_AVAILABLE


log = get_logger(__name__)


class FaissIndex:
    """Dense vector index backed by FAISS."""

    def __init__(self, chunks: List[Tuple[str, str, dict]], embedder: DenseEmbedder | None = None) -> None:
        if not _FAISS_AVAILABLE:
            raise ImportError("faiss is not available")
        self.ids = [c[0] for c in chunks]
        self.texts = [c[1] for c in chunks]
        self.metas = [c[2] for c in chunks]
        self.embedder = embedder or SiliconFlowEmbedder()
        embeddings = self.embedder.embed(self.texts)
        self._index = self._build_index(embeddings)

    def _build_index(self, vectors: List[List[float]]):
        matrix = np.asarray(vectors, dtype="float32")
        if matrix.ndim != 2 or matrix.shape[1] == 0:
            raise ValueError("invalid embedding matrix shape for faiss index")
        if matrix.size == 0:
            raise ValueError("cannot build faiss index from empty vectors")
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        return index

    def query(self, q: str, top_k: int = 8) -> List[Retrieved]:
        if not self.ids:
            return []
        qv = self.embedder.embed([q])
        if not qv or not qv[0]:
            log.warning("faiss_query_empty_embedding", query_length=len(q))
            return []
        matrix = np.asarray(qv, dtype="float32")
        if matrix.ndim != 2:
            log.warning("faiss_query_invalid_embedding", query_length=len(q), ndim=matrix.ndim)
            return []
        expected_dim = getattr(self._index, "d", None)
        actual_dim = matrix.shape[1]
        if expected_dim is not None and expected_dim != actual_dim:
            log.warning(
                "faiss_query_dim_mismatch",
                expected_dim=int(expected_dim),
                actual_dim=int(actual_dim),
            )
            return []
        faiss.normalize_L2(matrix)
        scores, indices = self._index.search(matrix, min(top_k, len(self.ids)))
        results: List[Retrieved] = []
        if indices.size == 0:
            return results
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0 or idx >= len(self.ids):
                continue
            results.append(
                Retrieved(
                    chunk_id=self.ids[idx],
                    text=self.texts[idx],
                    score=float(score),
                    meta=self.metas[idx],
                )
            )
        return results
