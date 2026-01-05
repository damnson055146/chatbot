import time

import pytest
from fastapi import HTTPException

from src.utils import security


@pytest.fixture(autouse=True)
def reset_security_state(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEYS", raising=False)
    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(security, "_admin_keys", None)
    monkeypatch.setattr(security, "_rate_limiter", None)


def test_verify_api_key_with_admin_keys(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEYS", "ops:secret")

    with pytest.raises(HTTPException):
        security.verify_api_key("incorrect")

    with pytest.raises(HTTPException):
        security.verify_api_key(None)

    security.verify_api_key("secret")


def test_verify_api_key_with_default_token(monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "token")

    security.verify_api_key("token")

    with pytest.raises(HTTPException):
        security.verify_api_key("other")


def test_verify_api_key_allows_anonymous_without_config():
    security.verify_api_key(None)

    with pytest.raises(HTTPException):
        security.verify_api_key("unexpected")


def test_rate_limiter_enforces_limit():
    limiter = security.RateLimiter(limit=2, window_seconds=60)

    limiter.allow("client")
    limiter.allow("client")

    with pytest.raises(HTTPException):
        limiter.allow("client")


def test_rate_limiter_window_allows_after_interval(monkeypatch):
    limiter = security.RateLimiter(limit=1, window_seconds=1)

    limiter.allow("client")

    # Move clock forward beyond window
    original_time = time.time
    monkeypatch.setattr(time, "time", lambda: original_time() + 2)

    limiter.allow("client")


def test_assert_admin_allows_readonly_with_flag():
    principal = security.Principal(role="admin_readonly", actor="readonly", sub="readonly", method="jwt")

    security.assert_admin(principal, allow_readonly=True)

    with pytest.raises(HTTPException) as exc_info:
        security.assert_admin(principal)
    assert exc_info.value.status_code == 403
