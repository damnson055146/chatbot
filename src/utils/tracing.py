from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from src.utils.logging import get_logger

try:  # pragma: no cover - optional dependency
    from opentelemetry import trace
    from opentelemetry.trace import Span
except ImportError:  # pragma: no cover - fallback when OTel missing
    trace = None
    Span = None  # type: ignore[assignment]

log = get_logger(__name__)

_CONFIGURED = False


def _parse_headers(raw: str) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for pair in raw.split(','):
        if not pair.strip() or '=' not in pair:
            continue
        key, value = pair.split('=', 1)
        key = key.strip()
        value = value.strip()
        if key:
            headers[key] = value
    return headers


def configure_tracing(service_name: str | None = None) -> None:
    """Initialise OpenTelemetry tracing if the SDK and exporter are available."""

    global _CONFIGURED
    if _CONFIGURED:
        return
    if trace is None:
        log.debug('tracing_disabled_no_sdk')
        return
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    except ImportError:  # pragma: no cover - optional extras missing
        log.info('tracing_sdk_missing')
        return

    endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')
    if not endpoint:
        log.debug('tracing_disabled_no_endpoint')
        return

    sample_ratio_raw = os.getenv('TRACING_SAMPLE_RATIO', '0.1')
    try:
        sample_ratio = float(sample_ratio_raw)
    except ValueError:
        log.warning('tracing_sample_ratio_invalid', value=sample_ratio_raw)
        sample_ratio = 0.1
    # clamp between 0 and 1
    sample_ratio = max(min(sample_ratio, 1.0), 0.0)
    if sample_ratio <= 0.0:
        log.debug('tracing_disabled_zero_sample')
        return

    headers_env = os.getenv('OTEL_EXPORTER_OTLP_HEADERS')
    headers = _parse_headers(headers_env) if headers_env else None
    insecure = os.getenv('OTEL_EXPORTER_OTLP_INSECURE', 'false').lower() in {'1', 'true', 'yes'}
    service = service_name or os.getenv('OTEL_SERVICE_NAME', 'study-abroad-rag')

    try:
        resource = Resource.create({'service.name': service})
        sampler = ParentBased(TraceIdRatioBased(sample_ratio))
        provider = TracerProvider(resource=resource, sampler=sampler)
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers=headers,
            insecure=insecure,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except Exception as exc:  # pragma: no cover - configuration failure
        log.warning('tracing_configuration_failed', error=str(exc))
        return

    _CONFIGURED = True
    log.info(
        'tracing_configured',
        endpoint=endpoint,
        sample_ratio=sample_ratio,
        service=service,
        insecure=insecure,
    )


def _get_tracer():
    if trace is None:
        return None
    try:
        return trace.get_tracer('src.utils.tracing')
    except Exception as exc:  # pragma: no cover - defensive
        log.debug('tracing_tracer_error', error=str(exc))
        return None


@contextmanager
def start_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Iterator[Optional['Span']]:
    tracer = _get_tracer()
    if tracer is None:
        yield None
        return
    span_cm = tracer.start_as_current_span(name)
    span = span_cm.__enter__()
    try:
        if attributes and span is not None:
            for key, value in attributes.items():
                try:
                    span.set_attribute(key, value)
                except Exception:  # pragma: no cover - ignore attribute errors
                    pass
        yield span
    except Exception as exc:
        if span is not None:
            try:
                span.record_exception(exc)
                span.set_attribute('error', True)
            except Exception:  # pragma: no cover
                pass
        raise
    finally:
        span_cm.__exit__(None, None, None)
