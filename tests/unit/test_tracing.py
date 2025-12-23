from src.utils.tracing import start_span


def test_start_span_no_op_without_tracer():
    with start_span("test-span", {"foo": "bar"}) as span:
        assert span is None
