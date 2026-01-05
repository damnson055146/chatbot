from __future__ import annotations

import asyncio
import base64
import math
import threading
import time
import os
import json
import re
from collections.abc import AsyncIterator
from typing import Any, Callable, Dict, List, Sequence, Tuple

import httpx
from tenacity import AsyncRetrying, retry, stop_after_attempt, wait_exponential

from src.utils.logging import get_logger
from src.utils.observability import get_metrics
from src.utils.tracing import start_span

log = get_logger(__name__)

_DEFAULT_BASE = "https://api.siliconflow.cn/v1"
_DEFAULT_CHAT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
_DEFAULT_EMBED_MODEL = "Qwen/Qwen3-Embedding-8B"
_DEFAULT_RERANK_MODEL = "Qwen/Qwen3-Reranker-8B"
_DEFAULT_STT_MODEL = "FunAudioLLM/SenseVoiceSmall"
_DEFAULT_OCR_MODEL = "Qwen/Qwen3-VL-32B-Instruct"


class SiliconFlowConfigError(RuntimeError):
    """Raised when SiliconFlow credentials or configuration are missing."""


def _base_url() -> str:
    return os.getenv("SILICONFLOW_BASE", _DEFAULT_BASE)


def _api_key() -> str | None:
    return os.getenv("SILICONFLOW_API_KEY")


def _enabled() -> bool:
    return bool(_api_key())


def _headers() -> Dict[str, str]:
    key = _api_key()
    if not key:
        raise SiliconFlowConfigError("SILICONFLOW_API_KEY is not configured")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _pseudo_embedding(text: str) -> List[float]:
    buckets = [0.0] * 64
    for token in text.lower().split():
        idx = hash(token) % 64
        buckets[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in buckets)) or 1.0
    return [v / norm for v in buckets]


def _default_embed_model() -> str:
    return os.getenv("SILICONFLOW_EMBED_MODEL", _DEFAULT_EMBED_MODEL)


def _embed_batch_size() -> int:
    return _get_int_env("SILICONFLOW_EMBED_BATCH_SIZE", 32)


def _embed_batch_max_chars() -> int:
    return _get_int_env("SILICONFLOW_EMBED_BATCH_MAX_CHARS", 12000)


def _default_rerank_model() -> str:
    return os.getenv("SILICONFLOW_RERANK_MODEL", _DEFAULT_RERANK_MODEL)


def _default_stt_model() -> str:
    return os.getenv("SILICONFLOW_STT_MODEL", _DEFAULT_STT_MODEL)


def _default_ocr_model() -> str:
    return os.getenv("SILICONFLOW_OCR_MODEL", _DEFAULT_OCR_MODEL)


def _to_data_url(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _clean_ocr_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def transcribe_audio(
    content: bytes,
    *,
    filename: str,
    mime_type: str,
    language: str | None = None,
    model: str | None = None,
) -> Dict[str, Any]:
    if not _enabled():
        raise SiliconFlowConfigError("SILICONFLOW_API_KEY is not configured")

    payload: Dict[str, Any] = {"model": model or _default_stt_model()}
    if language:
        payload["language"] = language

    files = {"file": (filename, content, mime_type)}
    headers = {"Authorization": f"Bearer {_api_key()}"}

    with httpx.Client(timeout=60.0) as client:
        response = client.post(f"{_base_url()}/audio/transcriptions", headers=headers, data=payload, files=files)
        response.raise_for_status()
        return response.json()


def ocr_image(
    content: bytes,
    *,
    filename: str,
    mime_type: str,
    model: str | None = None,
    prompt: str | None = None,
) -> Dict[str, Any]:
    if not _enabled():
        raise SiliconFlowConfigError("SILICONFLOW_API_KEY is not configured")

    ocr_prompt = prompt or (
        "Extract all readable text from the image. "
        "Return plain text only, preserve line breaks, and do not add commentary."
    )
    payload: Dict[str, Any] = {
        "model": model or _default_ocr_model(),
        "messages": _multimodal_messages(ocr_prompt, "You are an OCR engine.", [_to_data_url(content, mime_type)]),
        "temperature": 0.0,
        "max_tokens": 2048,
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(f"{_base_url()}/chat/completions", headers=_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {"text": _clean_ocr_text(str(text)), "model": payload["model"], "filename": filename}


def _get_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        log.warning("siliconflow_invalid_float_env", name=name, value=value)
        return default
    return parsed if parsed > 0 else default


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        log.warning("siliconflow_invalid_int_env", name=name, value=value)
        return default
    return parsed if parsed > 0 else default


def _rerank_timeout_seconds() -> float:
    return _get_float_env("SILICONFLOW_RERANK_TIMEOUT_SECONDS", 30.0)


def _rerank_max_attempts() -> int:
    disable_flag = os.getenv("SILICONFLOW_RERANK_DISABLE_RETRY")
    if disable_flag and disable_flag.strip().lower() in {"1", "true", "yes"}:
        return 1
    return _get_int_env("SILICONFLOW_RERANK_MAX_ATTEMPTS", 3)


def _rerank_backoff_min_seconds() -> float:
    return _get_float_env("SILICONFLOW_RERANK_BACKOFF_MIN_SECONDS", 1.0)


def _rerank_backoff_max_seconds() -> float:
    return _get_float_env("SILICONFLOW_RERANK_BACKOFF_MAX_SECONDS", 8.0)


def _rerank_cb_failure_threshold() -> int:
    return _get_int_env("SILICONFLOW_RERANK_CB_FAILURE_THRESHOLD", 5)


def _rerank_cb_reset_seconds() -> float:
    return _get_float_env("SILICONFLOW_RERANK_CB_RESET_SECONDS", 30.0)


def _chat_stream_max_attempts() -> int:
    return max(_get_int_env("SILICONFLOW_CHAT_STREAM_MAX_ATTEMPTS", 3), 1)


def _chat_stream_backoff_min_seconds() -> float:
    return _get_float_env("SILICONFLOW_CHAT_STREAM_BACKOFF_MIN_SECONDS", 1.0)


def _chat_stream_backoff_max_seconds() -> float:
    return _get_float_env("SILICONFLOW_CHAT_STREAM_BACKOFF_MAX_SECONDS", 8.0)


def _should_retry_stream_http_status(status_code: int) -> bool:
    if status_code == 429:
        return True
    if status_code in {408, 409}:
        return True
    return 500 <= status_code <= 599


def _parse_retry_after_seconds(headers: httpx.Headers) -> float | None:
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


class _CircuitBreaker:
    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._lock = threading.Lock()
        self._failure_count = 0
        self._state = "closed"
        self._opened_at = 0.0
        self._monotonic = monotonic

    def reset(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = "closed"
            self._opened_at = 0.0

    def should_skip(self, threshold: int, reset_seconds: float) -> bool:
        if threshold <= 0:
            if self._state != "closed":
                self.reset()
            return False
        now = self._monotonic()
        with self._lock:
            if self._state != "open":
                return False
            if now - self._opened_at >= reset_seconds:
                self._state = "half_open"
                self._failure_count = max(threshold - 1, 0)
                return False
            return True

    def record_failure(self, threshold: int) -> bool:
        if threshold <= 0:
            return False
        now = self._monotonic()
        with self._lock:
            if self._state == "open":
                self._opened_at = now
                return False
            self._failure_count = min(self._failure_count + 1, threshold)
            if self._failure_count >= threshold:
                self._state = "open"
                self._opened_at = now
                return True
            self._state = "closed"
            return False

    def record_success(self) -> bool:
        with self._lock:
            previous_state = self._state
            self._failure_count = 0
            self._state = "closed"
            self._opened_at = 0.0
        return previous_state in {"open", "half_open"}


_RERANK_CIRCUIT = _CircuitBreaker()


def reset_rerank_circuit() -> None:
    _RERANK_CIRCUIT.reset()


def _record_rerank_failure(
    metrics,
    threshold: int,
    reset_seconds: float,
    trace_id: str | None,
    lang_label: str | None = None,
) -> None:
    if threshold <= 0:
        return
    if lang_label:
        metrics.increment_counter(f"rerank_language_fallback::{lang_label}")
    opened = _RERANK_CIRCUIT.record_failure(threshold)
    if opened:
        metrics.increment_counter("rerank_circuit::opened")
        log.warning(
            "siliconflow_rerank_circuit_opened",
            threshold=threshold,
            cooldown=reset_seconds,
            trace_id=trace_id,
        )


def _fallback_scores(documents: Sequence[str]) -> List[Tuple[int, float]]:
    return [(idx, float(len(documents) - idx)) for idx in range(len(documents))]


def _chunk_embed_inputs(
    texts: Sequence[str],
    max_batch_size: int,
    max_batch_chars: int,
) -> List[Tuple[int, List[str]]]:
    batches: List[Tuple[int, List[str]]] = []
    batch: List[str] = []
    batch_chars = 0
    batch_start = 0
    for idx, text in enumerate(texts):
        text_len = len(text)
        if batch and (len(batch) >= max_batch_size or batch_chars + text_len > max_batch_chars):
            batches.append((batch_start, batch))
            batch = []
            batch_chars = 0
        if not batch:
            batch_start = idx
        batch.append(text)
        batch_chars += text_len
        if len(batch) >= max_batch_size:
            batches.append((batch_start, batch))
            batch = []
            batch_chars = 0
    if batch:
        batches.append((batch_start, batch))
    return batches


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3))
async def chat(
    prompt: str,
    *,
    system_message: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop: Sequence[str] | None = None,
    model: str | None = None,
    stream: bool = False,
) -> str:
    if not _enabled():
        return "[offline] Unable to call model. Provide key to enable generation."

    if stream:
        chunks: List[str] = []
        async for delta in chat_stream(
            prompt,
            system_message=system_message,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop,
            model=model,
        ):
            if delta:
                chunks.append(delta)
        return "".join(chunks).strip()

    payload = {
        "model": model or os.getenv("SILICONFLOW_MODEL", _DEFAULT_CHAT_MODEL),
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if stop:
        payload["stop"] = list(stop)
    payload["stream"] = stream

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(f"{_base_url()}/chat/completions", headers=_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


def _multimodal_messages(prompt: str, system_message: str, image_data_urls: Sequence[str]) -> List[Dict[str, Any]]:
    user_content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for url in image_data_urls:
        if not url:
            continue
        user_content.append({"type": "image_url", "image_url": {"url": url}})
    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_content},
    ]


async def chat_multimodal(
    prompt: str,
    *,
    system_message: str = "You are a helpful assistant.",
    image_data_urls: Sequence[str],
    temperature: float = 0.2,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop: Sequence[str] | None = None,
    model: str | None = None,
    stream: bool = False,
) -> str:
    if not _enabled():
        return "[offline] Unable to call model. Provide key to enable generation."

    if stream:
        chunks: List[str] = []
        async for delta in chat_multimodal_stream(
            prompt,
            system_message=system_message,
            image_data_urls=image_data_urls,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop,
            model=model,
        ):
            if delta:
                chunks.append(delta)
        return "".join(chunks).strip()

    payload: Dict[str, Any] = {
        "model": model or os.getenv("SILICONFLOW_MM_MODEL", "THUDM/GLM-4.1V"),
        "messages": _multimodal_messages(prompt, system_message, image_data_urls),
        "temperature": temperature,
        "stream": stream,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if stop:
        payload["stop"] = list(stop)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{_base_url()}/chat/completions", headers=_headers(), json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


async def chat_stream(
    prompt: str,
    *,
    system_message: str = "You are a helpful assistant.",
    temperature: float = 0.2,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop: Sequence[str] | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Stream chat completion deltas from SiliconFlow in an OpenAI-compatible SSE format.

    Yields text deltas (may be token-level or chunk-level depending on upstream behavior).
    """

    if not _enabled():
        yield "[offline] Unable to call model. Provide key to enable generation."
        return

    payload: Dict[str, Any] = {
        "model": model or os.getenv("SILICONFLOW_MODEL", _DEFAULT_CHAT_MODEL),
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "stream": True,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if stop:
        payload["stop"] = list(stop)

    metrics = get_metrics()
    max_attempts = _chat_stream_max_attempts()
    backoff_min = _chat_stream_backoff_min_seconds()
    backoff_max = _chat_stream_backoff_max_seconds()

    timeout = httpx.Timeout(30.0, read=None)
    async with httpx.AsyncClient(timeout=timeout) as client:
        attempt = 0
        while True:
            attempt += 1
            emitted_any = False
            try:
                async with client.stream(
                    "POST",
                    f"{_base_url()}/chat/completions",
                    headers=_headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        data = await response.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            emitted_any = True
                            yield str(content)
                        return

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        if raw == "[DONE]":
                            return
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        first = choices[0] or {}
                        delta = first.get("delta") or {}
                        content = delta.get("content")
                        if content is None:
                            message = first.get("message") or {}
                            content = message.get("content")
                        if content:
                            emitted_any = True
                            yield str(content)
                    return
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else 0
                retryable = _should_retry_stream_http_status(status_code)
                if (not retryable) or emitted_any or attempt >= max_attempts:
                    if attempt >= max_attempts and retryable and not emitted_any:
                        metrics.increment_counter("chat_stream_retry::exhausted")
                    raise
                metrics.increment_counter("chat_stream_retry::attempt")
                retry_after = _parse_retry_after_seconds(exc.response.headers) if exc.response is not None else None
                delay = min(backoff_max, backoff_min * (2 ** (attempt - 1)))
                if retry_after is not None:
                    delay = max(delay, min(retry_after, backoff_max))
                await asyncio.sleep(delay)
                continue
            except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError, httpx.TransportError) as exc:
                if emitted_any or attempt >= max_attempts:
                    if attempt >= max_attempts and not emitted_any:
                        metrics.increment_counter("chat_stream_retry::exhausted")
                    raise
                metrics.increment_counter("chat_stream_retry::attempt")
                delay = min(backoff_max, backoff_min * (2 ** (attempt - 1)))
                await asyncio.sleep(delay)
                continue


async def chat_multimodal_stream(
    prompt: str,
    *,
    system_message: str = "You are a helpful assistant.",
    image_data_urls: Sequence[str],
    temperature: float = 0.2,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop: Sequence[str] | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Stream multimodal chat completion deltas from SiliconFlow."""

    if not _enabled():
        yield "[offline] Unable to call model. Provide key to enable generation."
        return

    payload: Dict[str, Any] = {
        "model": model or os.getenv("SILICONFLOW_MM_MODEL", "THUDM/GLM-4.1V"),
        "messages": _multimodal_messages(prompt, system_message, image_data_urls),
        "temperature": temperature,
        "stream": True,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if stop:
        payload["stop"] = list(stop)

    metrics = get_metrics()
    max_attempts = _chat_stream_max_attempts()
    backoff_min = _chat_stream_backoff_min_seconds()
    backoff_max = _chat_stream_backoff_max_seconds()

    timeout = httpx.Timeout(60.0, read=None)
    async with httpx.AsyncClient(timeout=timeout) as client:
        attempt = 0
        while True:
            attempt += 1
            emitted_any = False
            try:
                async with client.stream(
                    "POST",
                    f"{_base_url()}/chat/completions",
                    headers=_headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        data = await response.json()
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            emitted_any = True
                            yield str(content)
                        return

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        if raw == "[DONE]":
                            return
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        first = choices[0] or {}
                        delta = first.get("delta") or {}
                        content = delta.get("content")
                        if content is None:
                            message = first.get("message") or {}
                            content = message.get("content")
                        if content:
                            emitted_any = True
                            yield str(content)
                    return
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else 0
                retryable = _should_retry_stream_http_status(status_code)
                if (not retryable) or emitted_any or attempt >= max_attempts:
                    if attempt >= max_attempts and retryable and not emitted_any:
                        metrics.increment_counter("chat_stream_retry::exhausted")
                    raise
                metrics.increment_counter("chat_stream_retry::attempt")
                retry_after = _parse_retry_after_seconds(exc.response.headers) if exc.response is not None else None
                delay = min(backoff_max, backoff_min * (2 ** (attempt - 1)))
                if retry_after is not None:
                    delay = max(delay, min(retry_after, backoff_max))
                await asyncio.sleep(delay)
                continue
            except (httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError, httpx.TransportError):
                if emitted_any or attempt >= max_attempts:
                    if attempt >= max_attempts and not emitted_any:
                        metrics.increment_counter("chat_stream_retry::exhausted")
                    raise
                metrics.increment_counter("chat_stream_retry::attempt")
                delay = min(backoff_max, backoff_min * (2 ** (attempt - 1)))
                await asyncio.sleep(delay)
                continue


def embed_texts(texts: Sequence[str], *, model: str | None = None) -> List[List[float]]:
    if not texts:
        return []
    if not _enabled():
        return [_pseudo_embedding(text) for text in texts]

    batch_size = _embed_batch_size()
    batch_max_chars = _embed_batch_max_chars()
    batches = _chunk_embed_inputs(texts, batch_size, batch_max_chars)
    embeddings: List[List[float]] = []
    expected_dim: int | None = None
    try:
        with httpx.Client(timeout=30.0) as client:
            for batch_start, batch in batches:
                payload = {"model": model or _default_embed_model(), "input": list(batch)}
                try:
                    response = client.post(f"{_base_url()}/embeddings", headers=_headers(), json=payload)
                    response.raise_for_status()
                    data = response.json().get("data", [])
                    batch_embeddings: List[List[float]] = []
                    for item in data:
                        vec = item.get("embedding")
                        if isinstance(vec, list):
                            batch_embeddings.append(vec)
                    if len(batch_embeddings) != len(batch):
                        log.warning(
                            "siliconflow_embed_incomplete",
                            expected=len(batch),
                            received=len(batch_embeddings),
                            batch_start=batch_start,
                        )
                        raise ValueError("embedding batch incomplete")
                    if not batch_embeddings:
                        log.warning("siliconflow_embed_empty", batch_start=batch_start)
                        raise ValueError("embedding batch empty")
                    if expected_dim is None:
                        expected_dim = len(batch_embeddings[0])
                    if any(len(vec) != expected_dim for vec in batch_embeddings):
                        log.warning(
                            "siliconflow_embed_dim_mismatch",
                            expected_dim=expected_dim,
                            batch_start=batch_start,
                        )
                        raise ValueError("embedding dimension mismatch")
                    embeddings.extend(batch_embeddings)
                except Exception as exc:
                    log.warning(
                        "siliconflow_embed_batch_failed",
                        error=str(exc),
                        batch_start=batch_start,
                        batch_size=len(batch),
                    )
                    return [_pseudo_embedding(text) for text in texts]
            if len(embeddings) == len(texts):
                return embeddings
            log.warning("siliconflow_embed_incomplete", expected=len(texts), received=len(embeddings))
    except Exception as exc:  # pragma: no cover - log and fall back
        log.warning("siliconflow_embed_fallback", error=str(exc))
    return [_pseudo_embedding(text) for text in texts]


async def rerank_async(
    query: str,
    documents: Sequence[str],
    *,
    model: str | None = None,
    trace_id: str | None = None,
    language: str | None = None,
) -> List[Tuple[int, float]]:
    if not documents:
        return []

    metrics = get_metrics()
    lang_label = (language or "unknown").lower()

    if not _enabled():
        metrics.increment_counter("rerank_fallback::disabled")
        metrics.increment_counter(f"rerank_language_fallback::{lang_label}")
        return _fallback_scores(documents)

    max_attempts = max(_rerank_max_attempts(), 1)
    failure_threshold = _rerank_cb_failure_threshold()
    reset_seconds = _rerank_cb_reset_seconds()

    span_attributes = {
        "trace_id": trace_id or "",
        "language": lang_label,
        "max_attempts": float(max_attempts),
        "failure_threshold": float(failure_threshold),
    }

    with start_span("siliconflow.rerank", span_attributes) as span:
        if _RERANK_CIRCUIT.should_skip(failure_threshold, reset_seconds):
            metrics.increment_counter("rerank_circuit::open_skip")
            metrics.increment_counter("rerank_fallback::circuit_open")
            metrics.increment_counter(f"rerank_language_fallback::{lang_label}")
            if span is not None:
                span.add_event(
                    "circuit_skip",
                    {"cooldown": reset_seconds, "threshold": failure_threshold},
                )
            log.warning(
                "siliconflow_rerank_circuit_skip",
                trace_id=trace_id,
                cooldown=reset_seconds,
                threshold=failure_threshold,
                language=lang_label,
            )
            return _fallback_scores(documents)

        payload = {
            "model": model or _default_rerank_model(),
            "query": query,
            "documents": list(documents),
        }
        timeout = _rerank_timeout_seconds()
        backoff_min = _rerank_backoff_min_seconds()
        backoff_max = max(backoff_min, _rerank_backoff_max_seconds())

        last_attempt_number = 0
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async for attempt in AsyncRetrying(
                    wait=wait_exponential(multiplier=1, min=backoff_min, max=backoff_max),
                    stop=stop_after_attempt(max_attempts),
                    reraise=True,
                ):
                    last_attempt_number = attempt.retry_state.attempt_number
                    if span is not None:
                        span.add_event(
                            "rerank_attempt",
                            {
                                "attempt": last_attempt_number,
                                "idle_for": float(attempt.retry_state.idle_for or 0.0),
                            },
                        )
                    if last_attempt_number > 1:
                        metrics.increment_counter("rerank_retry::attempt")
                        log.warning(
                            "siliconflow_rerank_retry",
                            attempt=last_attempt_number,
                            idle_for=attempt.retry_state.idle_for,
                            trace_id=trace_id,
                            max_attempts=max_attempts,
                            language=lang_label,
                        )
                    with attempt:
                        response = await client.post(
                            f"{_base_url()}/rerank",
                            headers=_headers(),
                            json=payload,
                            timeout=timeout,
                        )
                        response.raise_for_status()
                        data = response.json().get("data", [])
                        results: List[Tuple[int, float]] = []
                        for item in data:
                            idx = item.get("index")
                            score = item.get("score")
                            if isinstance(idx, int) and 0 <= idx < len(documents):
                                try:
                                    score_value = float(score)
                                except (TypeError, ValueError):
                                    score_value = 0.0
                                results.append((idx, score_value))
                        if results:
                            recovered = _RERANK_CIRCUIT.record_success()
                            if recovered:
                                metrics.increment_counter("rerank_circuit::recovered")
                                metrics.increment_counter(f"rerank_language_recovered::{lang_label}")
                                if span is not None:
                                    span.add_event("circuit_recovered")
                                log.info(
                                    "siliconflow_rerank_circuit_recovered",
                                    trace_id=trace_id,
                                    threshold=failure_threshold,
                                    language=lang_label,
                                )
                            if last_attempt_number > 1:
                                metrics.increment_counter("rerank_retry::success_after_retry")
                            return results
                        log.warning(
                            "siliconflow_rerank_empty",
                            count=len(documents),
                            trace_id=trace_id,
                            language=lang_label,
                        )
                        metrics.increment_counter("rerank_fallback::empty_response")
                        _record_rerank_failure(
                            metrics,
                            failure_threshold,
                            reset_seconds,
                            trace_id,
                            lang_label,
                        )
                        if span is not None:
                            span.add_event("empty_response")
                        return _fallback_scores(documents)
        except Exception as exc:  # pragma: no cover - observability + fallback
            attempts_used = max(last_attempt_number, 1)
            if attempts_used >= max_attempts:
                metrics.increment_counter("rerank_retry::exhausted")
            metrics.increment_counter("rerank_fallback::error")
            log.warning(
                "siliconflow_rerank_fallback",
                error=str(exc),
                attempts=attempts_used,
                max_attempts=max_attempts,
                trace_id=trace_id,
                language=lang_label,
            )
            _record_rerank_failure(
                metrics,
                failure_threshold,
                reset_seconds,
                trace_id,
                lang_label,
            )
            if span is not None:
                span.add_event(
                    "exception",
                    {"attempts": attempts_used, "error": str(exc)},
                )
            return _fallback_scores(documents)

    _record_rerank_failure(
        metrics,
        failure_threshold,
        reset_seconds,
        trace_id,
        lang_label,
    )
    return _fallback_scores(documents)



def rerank(
    query: str,
    documents: Sequence[str],
    *,
    model: str | None = None,
    trace_id: str | None = None,
) -> List[Tuple[int, float]]:
    """Synchronous wrapper retained for backwards compatibility."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        raise RuntimeError(
            "siliconflow.rerank cannot be called from an active event loop. Use rerank_async instead."
        )
    return asyncio.run(rerank_async(query, documents, model=model, trace_id=trace_id))
