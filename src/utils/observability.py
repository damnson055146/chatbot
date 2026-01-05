from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import UTC, datetime
import time
from typing import Any, Deque, Dict, List

import copy

from src.schemas.models import ServiceStatusCategory, ServiceStatusMetric, ServiceStatusResponse

MetricsSnapshot = Dict[str, Dict[str, float]]


_LATENCY_SLO_P95 = {
    "retrieval": 800.0,
    "rerank": 900.0,
    "generation": 3000.0,
    "end_to_end": 7000.0,
}

_EMPTY_RETRIEVAL_THRESHOLDS = (0.05, 0.15)
_LOW_CONFIDENCE_THRESHOLDS = (0.1, 0.2)


class RequestMetrics:
    def __init__(self, percentile_window: int = 200, history_window: int = 120) -> None:
        self._counts: Dict[str, int] = defaultdict(int)
        self._latency_sum: Dict[str, float] = defaultdict(float)
        self._latency_samples: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=percentile_window))
        self._phase_latency_sum: Dict[str, float] = defaultdict(float)
        self._phase_latency_samples: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=percentile_window))
        self._empty_retrievals: int = 0
        self._rerank_fallbacks: int = 0
        self._low_confidence: int = 0
        self._citation_coverage_samples: Deque[float] = deque(maxlen=percentile_window)
        self._retrieval_recall_samples: Deque[float] = deque(maxlen=percentile_window)
        self._retrieval_mrr_samples: Deque[float] = deque(maxlen=percentile_window)
        self._retrieval_eval_k: int | None = None
        self._counters: Dict[str, float] = defaultdict(float)
        self._history: Deque[Dict[str, Any]] = deque(maxlen=history_window)

    def record(self, endpoint: str, duration_ms: float) -> None:
        self._counts[endpoint] += 1
        self._latency_sum[endpoint] += duration_ms
        self._latency_samples[endpoint].append(duration_ms)

    def record_phase(self, phase: str, duration_ms: float) -> None:
        self._phase_latency_sum[phase] += duration_ms
        self._phase_latency_samples[phase].append(duration_ms)

    def record_empty_retrieval(self) -> None:
        self._empty_retrievals += 1

    def record_rerank_fallback(self) -> None:
        self._rerank_fallbacks += 1

    def record_low_confidence(self) -> None:
        self._low_confidence += 1

    def record_citation_coverage(self, citation_count: int, required: int) -> None:
        denominator = max(required, 1)
        coverage = min(max(citation_count / denominator, 0.0), 1.0)
        self._citation_coverage_samples.append(coverage)

    def record_retrieval_eval(self, recall_at_k: float, mrr: float, k: int) -> None:
        recall = min(max(recall_at_k, 0.0), 1.0)
        rank = min(max(mrr, 0.0), 1.0)
        self._retrieval_recall_samples.append(recall)
        self._retrieval_mrr_samples.append(rank)
        self._retrieval_eval_k = int(k)

    def increment_counter(self, name: str, amount: float = 1.0) -> None:
        self._counters[name] += amount

    def snapshot(self) -> MetricsSnapshot:
        data: MetricsSnapshot = {}
        for endpoint, count in self._counts.items():
            samples = list(self._latency_samples[endpoint])
            percentiles = _compute_percentiles(samples)
            data[endpoint] = {
                "count": float(count),
                "avg_latency_ms": (self._latency_sum[endpoint] / count) if count else 0.0,
                "p50_latency_ms": percentiles.get(50, 0.0),
                "p95_latency_ms": percentiles.get(95, 0.0),
            }
        phase_block: Dict[str, Dict[str, float]] = {}
        for phase, samples in self._phase_latency_samples.items():
            phase_samples = list(samples)
            percentiles = _compute_percentiles(phase_samples)
            total_count = len(phase_samples)
            phase_block[phase] = {
                "count": float(total_count),
                "avg_latency_ms": (self._phase_latency_sum[phase] / total_count) if total_count else 0.0,
                "p50_latency_ms": percentiles.get(50, 0.0),
                "p95_latency_ms": percentiles.get(95, 0.0),
            }
        if phase_block:
            data["phases"] = phase_block
        diagnostics = {
            "empty_retrievals": float(self._empty_retrievals),
            "rerank_fallbacks": float(self._rerank_fallbacks),
            "low_confidence_answers": float(self._low_confidence),
        }
        if self._citation_coverage_samples:
            citation_percentiles = _compute_percentiles(list(self._citation_coverage_samples))
            diagnostics["citation_coverage_avg"] = sum(self._citation_coverage_samples) / len(self._citation_coverage_samples)
            diagnostics["citation_coverage_p50"] = citation_percentiles.get(50, 0.0)
            diagnostics["citation_coverage_p95"] = citation_percentiles.get(95, 0.0)
        if self._retrieval_recall_samples:
            recall_percentiles = _compute_percentiles(list(self._retrieval_recall_samples))
            mrr_percentiles = _compute_percentiles(list(self._retrieval_mrr_samples))
            diagnostics["retrieval_recall_avg"] = sum(self._retrieval_recall_samples) / len(self._retrieval_recall_samples)
            diagnostics["retrieval_recall_p50"] = recall_percentiles.get(50, 0.0)
            diagnostics["retrieval_recall_p95"] = recall_percentiles.get(95, 0.0)
            diagnostics["retrieval_mrr_avg"] = sum(self._retrieval_mrr_samples) / len(self._retrieval_mrr_samples)
            diagnostics["retrieval_mrr_p50"] = mrr_percentiles.get(50, 0.0)
            diagnostics["retrieval_mrr_p95"] = mrr_percentiles.get(95, 0.0)
            if self._retrieval_eval_k is not None:
                diagnostics["retrieval_eval_k"] = float(self._retrieval_eval_k)
        data["diagnostics"] = diagnostics

        data["status"] = _build_status_block(
            phase_block,
            diagnostics,
            self._counts.get("/v1/query", 0),
            self._empty_retrievals,
            self._low_confidence,
        )
        if self._counters:
            data["counters"] = dict(self._counters)
        return data

    def record_snapshot(self, snapshot: Dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now(UTC),
            "snapshot": copy.deepcopy(snapshot),
        }
        self._history.append(entry)

    def history(self, limit: int = 30) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        entries = list(self._history)
        return entries[-limit:] if limit else entries

    def reset(self) -> None:
        self._counts.clear()
        self._latency_sum.clear()
        self._latency_samples.clear()
        self._phase_latency_sum.clear()
        self._phase_latency_samples.clear()
        self._empty_retrievals = 0
        self._rerank_fallbacks = 0
        self._low_confidence = 0
        self._citation_coverage_samples.clear()
        self._retrieval_recall_samples.clear()
        self._retrieval_mrr_samples.clear()
        self._retrieval_eval_k = None
        self._counters.clear()
        self._history.clear()


@contextmanager
def time_phase(metrics: "RequestMetrics", phase: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        metrics.record_phase(phase, (time.perf_counter() - start) * 1000)


@contextmanager
def time_phase_endpoint(metrics: "RequestMetrics", phase: str, endpoint: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        metrics.record_phase(phase, duration_ms)
        metrics.record(endpoint, duration_ms)

def _compute_percentiles(samples: List[float]) -> Dict[int, float]:
    if not samples:
        return {}
    ordered = sorted(samples)
    results: Dict[int, float] = {}
    for percentile in (50, 95):
        index = int(round((percentile / 100) * (len(ordered) - 1)))
        index = min(max(index, 0), len(ordered) - 1)
        results[percentile] = ordered[index]
    return results


def _build_status_block(
    phases: Dict[str, Dict[str, float]],
    diagnostics: Dict[str, float],
    query_count: int,
    empty_retrievals: int,
    low_confidence: int,
) -> Dict[str, Dict[str, Dict[str, float]]]:
    latency_status: Dict[str, Dict[str, float]] = {}
    for phase, values in phases.items():
        p95 = values.get("p95_latency_ms", 0.0)
        slo = _LATENCY_SLO_P95.get(phase)
        if slo is None:
            continue
        latency_status[phase] = {
            "p95_latency_ms": p95,
            "slo_p95_ms": slo,
            "status": _classify_status(p95, slo),
        }
    if "end_to_end" not in latency_status and "end_to_end" in phases:
        p95 = phases["end_to_end"].get("p95_latency_ms", 0.0)
        latency_status["end_to_end"] = {
            "p95_latency_ms": p95,
            "slo_p95_ms": _LATENCY_SLO_P95["end_to_end"],
            "status": _classify_status(p95, _LATENCY_SLO_P95["end_to_end"]),
        }

    empty_rate = (empty_retrievals / query_count) if query_count else 0.0
    low_conf_rate = (low_confidence / query_count) if query_count else 0.0

    quality_status = {
        "empty_retrieval_rate": {
            "value": empty_rate,
            "status": _classify_rate(empty_rate, _EMPTY_RETRIEVAL_THRESHOLDS),
            "thresholds": {
                "green": _EMPTY_RETRIEVAL_THRESHOLDS[0],
                "amber": _EMPTY_RETRIEVAL_THRESHOLDS[1],
            },
        },
        "low_confidence_rate": {
            "value": low_conf_rate,
            "status": _classify_rate(low_conf_rate, _LOW_CONFIDENCE_THRESHOLDS),
            "thresholds": {
                "green": _LOW_CONFIDENCE_THRESHOLDS[0],
                "amber": _LOW_CONFIDENCE_THRESHOLDS[1],
            },
        },
    }

    return {
        "latency": latency_status,
        "quality": quality_status,
    }


def _classify_status(value: float, slo: float) -> str:
    if value <= slo:
        return "green"
    if value <= slo * 1.25:
        return "amber"
    return "red"


def _classify_rate(value: float, thresholds: tuple[float, float]) -> str:
    green, amber = thresholds
    if value <= green:
        return "green"
    if value <= amber:
        return "amber"
    return "red"


_METRICS = RequestMetrics()


def get_metrics() -> RequestMetrics:
    return _METRICS


def get_service_status_snapshot(snapshot: MetricsSnapshot) -> ServiceStatusResponse:
    status_block = snapshot.get("status", {})
    categories: List[ServiceStatusCategory] = []

    latency_status = status_block.get("latency", {})
    latency_metrics: List[ServiceStatusMetric] = []
    for phase, payload in latency_status.items():
        latency_metrics.append(
            ServiceStatusMetric(
                name=f"latency_{phase}",
                status=str(payload.get("status", "unknown")),
                value=float(payload.get("p95_latency_ms", 0.0)),
                target=float(payload.get("slo_p95_ms", 0.0)),
            )
        )
    if latency_metrics:
        categories.append(ServiceStatusCategory(name="latency", metrics=latency_metrics))

    quality_status = status_block.get("quality", {})
    quality_metrics: List[ServiceStatusMetric] = []
    for key, payload in quality_status.items():
        quality_metrics.append(
            ServiceStatusMetric(
                name=key,
                status=str(payload.get("status", "unknown")),
                value=float(payload.get("value", 0.0)),
                target=float(payload.get("thresholds", {}).get("green", 0.0)),
                threshold_amber=float(payload.get("thresholds", {}).get("amber", 0.0)),
            )
        )
    if quality_metrics:
        categories.append(ServiceStatusCategory(name="quality", metrics=quality_metrics))

    return ServiceStatusResponse(categories=categories)
