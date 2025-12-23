import asyncio
import httpx
import pytest

from src.utils import siliconflow
from src.utils.observability import get_metrics


@pytest.fixture(autouse=True)
def clear_api_key(monkeypatch):
    managed_envs = [
        "SILICONFLOW_API_KEY",
        "SILICONFLOW_RERANK_MAX_ATTEMPTS",
        "SILICONFLOW_RERANK_TIMEOUT_SECONDS",
        "SILICONFLOW_RERANK_BACKOFF_MIN_SECONDS",
        "SILICONFLOW_RERANK_BACKOFF_MAX_SECONDS",
        "SILICONFLOW_RERANK_DISABLE_RETRY",
        "SILICONFLOW_RERANK_CB_FAILURE_THRESHOLD",
        "SILICONFLOW_RERANK_CB_RESET_SECONDS",
    ]
    for name in managed_envs:
        monkeypatch.delenv(name, raising=False)
    siliconflow.reset_rerank_circuit()
    get_metrics().reset()
    yield
    for name in managed_envs:
        monkeypatch.delenv(name, raising=False)
    siliconflow.reset_rerank_circuit()
    get_metrics().reset()


def test_chat_offline_returns_stub():
    result = asyncio.run(
        siliconflow.chat(
            "hello",
            system_message="test",
            temperature=0.5,
            top_p=0.9,
            max_tokens=50,
            stop=["stop"],
            model="custom-model",
        )
    )
    assert result.startswith("[offline]")


def test_embed_texts_fallback_without_key():
    texts = ["留学签证材料", "Scholarship application requirements"]
    vectors = siliconflow.embed_texts(texts)
    assert len(vectors) == len(texts)
    assert all(len(vec) == 64 for vec in vectors)


def test_rerank_preserves_order_without_key():
    docs = ["apple", "banana", "cherry"]
    scores = asyncio.run(siliconflow.rerank_async("fruit", docs))
    indices = [idx for idx, _ in scores]
    assert indices == [0, 1, 2]
    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_fallback::disabled"] >= 1


class _StubResponse:
    def __init__(self, data: list[dict[str, object]], status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "mock error",
                request=httpx.Request("POST", "https://mock"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict[str, object]:
        return {"data": self._data}


class _StubAsyncClient:
    def __init__(self, plan: list[object]) -> None:
        self._plan = plan

    async def __aenter__(self) -> "_StubAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(self, *args, **kwargs):
        if not self._plan:
            raise AssertionError("stub plan exhausted")
        action = self._plan.pop(0)
        if isinstance(action, Exception):
            raise action
        return action


def _patch_async_client(monkeypatch, plan: list[object]) -> None:
    def factory(*args, **kwargs):
        return _StubAsyncClient(list(plan))

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_rerank_retries_and_succeeds(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "dummy")

    request = httpx.Request("POST", "https://api.siliconflow.cn/v1/rerank")
    plan = [
        httpx.ReadTimeout("timeout", request=request),
        httpx.ConnectError("connect", request=request),
        _StubResponse(
            [
                {"index": 1, "score": 0.9},
                {"index": 0, "score": 0.5},
            ]
        ),
    ]
    _patch_async_client(monkeypatch, plan)

    docs = ["apple", "banana"]
    scores = asyncio.run(siliconflow.rerank_async("fruit", docs, trace_id="trace-123"))

    assert scores[0][0] == 1
    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_retry::attempt"] == 2.0
    assert counters["rerank_retry::success_after_retry"] == 1.0
    assert "rerank_retry::exhausted" not in counters
    assert "rerank_fallback::error" not in counters


def test_rerank_retries_exhaust(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "dummy")

    request = httpx.Request("POST", "https://api.siliconflow.cn/v1/rerank")
    plan = [
        httpx.ReadTimeout("timeout", request=request),
        httpx.ConnectError("connect1", request=request),
        httpx.ConnectError("connect2", request=request),
    ]
    _patch_async_client(monkeypatch, plan)

    docs = ["one", "two", "three"]
    scores = asyncio.run(siliconflow.rerank_async("numbers", docs, trace_id="trace-xyz"))

    indices = [idx for idx, _ in scores]
    assert indices == [0, 1, 2]
    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_retry::attempt"] == 2.0
    assert counters["rerank_retry::exhausted"] == 1.0
    assert counters["rerank_fallback::error"] == 1.0
    assert "rerank_retry::success_after_retry" not in counters


def test_rerank_disable_retry(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "dummy")
    monkeypatch.setenv("SILICONFLOW_RERANK_DISABLE_RETRY", "1")

    request = httpx.Request("POST", "https://api.siliconflow.cn/v1/rerank")
    plan = [httpx.ReadTimeout("timeout", request=request)]
    _patch_async_client(monkeypatch, plan)

    docs = ["alpha", "beta"]
    scores = asyncio.run(siliconflow.rerank_async("letters", docs, trace_id="trace-disable"))

    assert [idx for idx, _ in scores] == [0, 1]
    counters = get_metrics().snapshot().get("counters", {})
    assert "rerank_retry::attempt" not in counters
    assert counters["rerank_retry::exhausted"] == 1.0
    assert counters["rerank_fallback::error"] == 1.0



def test_rerank_max_attempts_respected(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "dummy")
    monkeypatch.setenv("SILICONFLOW_RERANK_MAX_ATTEMPTS", "2")

    request = httpx.Request("POST", "https://api.siliconflow.cn/v1/rerank")
    plan = [
        httpx.ReadTimeout("timeout", request=request),
        httpx.ConnectError("connect", request=request),
    ]
    _patch_async_client(monkeypatch, plan)

    docs = ["uno", "dos"]
    scores = asyncio.run(siliconflow.rerank_async("numbers", docs, trace_id="trace-attempts"))

    assert [idx for idx, _ in scores] == [0, 1]
    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_retry::attempt"] == 1.0
    assert counters["rerank_retry::exhausted"] == 1.0
    assert counters["rerank_fallback::error"] == 1.0


def test_rerank_circuit_opens_and_skips(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "dummy")
    monkeypatch.setenv("SILICONFLOW_RERANK_CB_FAILURE_THRESHOLD", "2")
    monkeypatch.setenv("SILICONFLOW_RERANK_CB_RESET_SECONDS", "60")
    monkeypatch.setenv("SILICONFLOW_RERANK_MAX_ATTEMPTS", "1")

    request = httpx.Request("POST", "https://api.siliconflow.cn/v1/rerank")

    _patch_async_client(monkeypatch, [httpx.ReadTimeout("timeout1", request=request)])
    asyncio.run(siliconflow.rerank_async("letters", ["alpha", "beta"], trace_id="cb-1"))

    _patch_async_client(monkeypatch, [httpx.ReadTimeout("timeout2", request=request)])
    asyncio.run(siliconflow.rerank_async("letters", ["alpha", "beta"], trace_id="cb-2"))

    _patch_async_client(
        monkeypatch,
        [
            _StubResponse(
                [
                    {"index": 0, "score": 0.6},
                    {"index": 1, "score": 0.5},
                ]
            )
        ],
    )
    scores = asyncio.run(siliconflow.rerank_async("letters", ["alpha", "beta"], trace_id="cb-3"))
    assert [idx for idx, _ in scores] == [0, 1]

    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_circuit::opened"] == 1.0
    assert counters["rerank_circuit::open_skip"] == 1.0
    assert counters["rerank_fallback::circuit_open"] == 1.0


def test_rerank_circuit_recovers_after_cooldown(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "dummy")
    monkeypatch.setenv("SILICONFLOW_RERANK_CB_FAILURE_THRESHOLD", "2")
    monkeypatch.setenv("SILICONFLOW_RERANK_CB_RESET_SECONDS", "0.01")
    monkeypatch.setenv("SILICONFLOW_RERANK_MAX_ATTEMPTS", "1")

    request = httpx.Request("POST", "https://api.siliconflow.cn/v1/rerank")

    _patch_async_client(monkeypatch, [httpx.ReadTimeout("timeout1", request=request)])
    asyncio.run(siliconflow.rerank_async("letters", ["alpha", "beta"], trace_id="cb-rec-1"))

    _patch_async_client(monkeypatch, [httpx.ReadTimeout("timeout2", request=request)])
    asyncio.run(siliconflow.rerank_async("letters", ["alpha", "beta"], trace_id="cb-rec-2"))

    siliconflow._RERANK_CIRCUIT._opened_at = siliconflow.time.monotonic() - 1.0

    _patch_async_client(
        monkeypatch,
        [
            _StubResponse(
                [
                    {"index": 1, "score": 0.9},
                    {"index": 0, "score": 0.5},
                ]
            )
        ],
    )
    scores = asyncio.run(siliconflow.rerank_async("letters", ["alpha", "beta"], trace_id="cb-rec-3"))
    assert [idx for idx, _ in scores] == [1, 0]

    counters = get_metrics().snapshot().get("counters", {})
    assert counters["rerank_circuit::opened"] == 1.0
    assert counters["rerank_circuit::recovered"] == 1.0
    assert "rerank_circuit::open_skip" not in counters or counters["rerank_circuit::open_skip"] == 0.0
