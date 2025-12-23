from __future__ import annotations

from typing import List

import os

from src.utils import siliconflow
from src.utils.index import Retrieved
from src.utils.logging import get_logger
from src.utils.observability import get_metrics

log = get_logger(__name__)


class SiliconFlowReranker:
    def __init__(self, model: str | None = None) -> None:
        self.model = model

    async def rerank(
        self,
        query: str,
        items: List[Retrieved],
        *,
        trace_id: str | None = None,
        language: str | None = None,
    ) -> List[Retrieved]:
        if not items:
            return items

        metrics = get_metrics()
        model_name = self.model or os.getenv("SILICONFLOW_RERANK_MODEL") or "default"
        metrics.increment_counter(f"rerank_model::{model_name}")

        lang_label = (language or "unknown").lower()
        metrics.increment_counter(f"rerank_language::{lang_label}")

        scores = await siliconflow.rerank_async(
            query,
            [item.text for item in items],
            model=self.model,
            trace_id=trace_id,
            language=language,
        )
        if not scores:
            log.warning("rerank_no_scores", count=len(items), trace_id=trace_id)
            metrics.increment_counter("rerank_fallback::empty_scores")
            metrics.increment_counter(f"rerank_language_fallback::{lang_label}")
            return items

        score_map = {idx: score for idx, score in scores}
        indexed_items = list(enumerate(items))
        ranked_pairs = sorted(
            indexed_items,
            key=lambda pair: (score_map.get(pair[0], float("-inf")), -pair[0]),
            reverse=True,
        )
        return [item for _, item in ranked_pairs]


def get_reranker() -> SiliconFlowReranker:
    return SiliconFlowReranker(os.getenv("SILICONFLOW_RERANK_MODEL"))
