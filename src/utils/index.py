from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from rank_bm25 import BM25Okapi

from src.utils import siliconflow


@dataclass
class Retrieved:
    chunk_id: str
    text: str
    score: float
    meta: dict


class DenseEmbedder:
    def embed(self, texts: List[str]) -> List[List[float]]:  # pragma: no cover - interface
        raise NotImplementedError


class SiliconFlowEmbedder(DenseEmbedder):
    def __init__(self, model: str | None = None) -> None:
        self.model = model

    def embed(self, texts: List[str]) -> List[List[float]]:
        return siliconflow.embed_texts(texts, model=self.model)


class DummyEmbedder(DenseEmbedder):
    def embed(self, texts: List[str]) -> List[List[float]]:
        # Fast, deterministic pseudo-embeddings using hash buckets
        vecs: List[List[float]] = []
        for t in texts:
            buckets = [0.0] * 64
            for w in t.lower().split():
                idx = hash(w) % 64
                buckets[idx] += 1.0
            # L2 normalize
            norm = math.sqrt(sum(v * v for v in buckets)) or 1.0
            vecs.append([v / norm for v in buckets])
        return vecs


def _cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class HybridIndex:
    def __init__(self, chunks: List[Tuple[str, str, dict]], embedder: DenseEmbedder | None = None) -> None:
        # chunks: List of (chunk_id, text, meta)
        self.ids = [c[0] for c in chunks]
        self.texts = [c[1] for c in chunks]
        self.metas = [c[2] for c in chunks]
        tokenized = [t.lower().split() for t in self.texts]
        self.bm25 = BM25Okapi(tokenized)
        self.embedder = embedder or SiliconFlowEmbedder()
        self.embeddings = self.embedder.embed(self.texts)

    def query(self, q: str, top_k: int = 8, alpha: float = 0.5) -> List[Retrieved]:
        # alpha: weight for dense vs lexical
        bm_scores = self.bm25.get_scores(q.lower().split())
        qv = self.embedder.embed([q])[0]
        den_scores = [_cosine(qv, v) for v in self.embeddings]
        results: List[Tuple[int, float]] = []
        for i, (b, d) in enumerate(zip(bm_scores, den_scores)):
            # scale bm25 roughly into 0..1 by dividing with max possible (heuristic)
            score = (1 - alpha) * (b / (max(bm_scores) or 1)) + alpha * d
            results.append((i, score))
        results.sort(key=lambda x: x[1], reverse=True)
        out: List[Retrieved] = []
        for idx, s in results[:top_k]:
            out.append(Retrieved(chunk_id=self.ids[idx], text=self.texts[idx], score=s, meta=self.metas[idx]))
        return out

