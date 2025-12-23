from src.utils.observability import (
    RequestMetrics,
    get_service_status_snapshot,
    time_phase,
    time_phase_endpoint,
)


def test_request_metrics_snapshot():
    metrics = RequestMetrics()
    metrics.record("/v1/query", 10.0)
    metrics.record("/v1/query", 20.0)
    metrics.record("/v1/ingest", 5.0)
    metrics.record_phase("retrieval", 12.0)
    metrics.record_phase("generation", 25.0)
    metrics.record_empty_retrieval()
    metrics.record_rerank_fallback()
    metrics.record_low_confidence()
    metrics.record_citation_coverage(1, 2)
    metrics.record_citation_coverage(2, 2)
    metrics.increment_counter("rerank_fallback::disabled")

    with time_phase(metrics, "phase_test"):
        pass

    with time_phase_endpoint(metrics, "phase_endpoint", "/custom"):
        pass

    snapshot = metrics.snapshot()
    assert snapshot["/v1/query"]["count"] == 2
    assert snapshot["/v1/query"]["avg_latency_ms"] == 15.0
    assert snapshot["/v1/query"]["p50_latency_ms"] == 10.0
    assert snapshot["/v1/query"]["p95_latency_ms"] == 20.0
    assert snapshot["/v1/ingest"]["count"] == 1

    phases = snapshot["phases"]
    assert phases["retrieval"]["count"] == 1
    assert phases["retrieval"]["avg_latency_ms"] == 12.0
    assert phases["generation"]["count"] == 1
    assert phases["generation"]["avg_latency_ms"] == 25.0
    assert phases["phase_test"]["count"] == 1
    assert snapshot["/custom"]["count"] == 1

    diagnostics = snapshot["diagnostics"]
    assert diagnostics["empty_retrievals"] == 1
    assert diagnostics["rerank_fallbacks"] == 1
    assert diagnostics["low_confidence_answers"] == 1
    assert diagnostics["citation_coverage_avg"] == 0.75

    status = snapshot["status"]
    assert "latency" in status and "quality" in status
    assert status["latency"]["retrieval"]["status"] == "green"
    assert status["quality"]["empty_retrieval_rate"]["value"] == 0.5

    counters = snapshot.get("counters", {})
    assert counters["rerank_fallback::disabled"] == 1

    service_status = get_service_status_snapshot(snapshot)
    assert service_status.categories
    assert any(cat.name == "latency" for cat in service_status.categories)

    metrics.reset()
    cleared = metrics.snapshot()
    assert cleared == {
        "diagnostics": {
            "empty_retrievals": 0.0,
            "rerank_fallbacks": 0.0,
            "low_confidence_answers": 0.0,
        },
        "status": {
            "latency": {},
            "quality": {
                "empty_retrieval_rate": {
                    "value": 0.0,
                    "status": "green",
                    "thresholds": {"green": 0.05, "amber": 0.15},
                },
                "low_confidence_rate": {
                    "value": 0.0,
                    "status": "green",
                    "thresholds": {"green": 0.1, "amber": 0.2},
                },
            },
        },
    }
