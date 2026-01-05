from __future__ import annotations

import os
import time
import base64
import hashlib
import hmac
import secrets
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict

from fastapi import HTTPException
import jwt


def verify_api_key(provided_key: str | None) -> None:
    valid_keys = _load_admin_keys()
    if valid_keys:
        if provided_key is None or provided_key not in valid_keys:
            raise HTTPException(status_code=401, detail="Invalid API token")
        return

    expected_default = os.getenv("API_AUTH_TOKEN")
    if expected_default:
        if provided_key != expected_default:
            raise HTTPException(status_code=401, detail="Invalid API token")
        return

    if provided_key is None:
        return

    raise HTTPException(status_code=401, detail="Invalid API token")


def hash_password(password: str, *, iterations: int | None = None) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256."""

    if iterations is None:
        raw = os.getenv("PASSWORD_HASH_ITERATIONS", "120000").strip()
        try:
            iterations = max(60000, int(raw))
        except ValueError:
            iterations = 120000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${iterations}${salt_b64}${digest_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a PBKDF2-HMAC-SHA256 hash."""

    try:
        scheme, iter_raw, salt_b64, digest_b64 = stored_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iter_raw)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
    except (ValueError, TypeError):
        return False
    computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(computed, expected)


@dataclass(frozen=True)
class Principal:
    """Authenticated caller identity.

    - role: "user" | "admin" | "admin_readonly"
    - actor: human-readable actor name used in audit logs
    - sub: stable identifier (for rate limiting / correlation)
    - method: "jwt" | "api_key" | "anonymous"
    """

    role: str
    actor: str
    sub: str
    method: str


def _truthy_env(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET is not configured")
    return secret


def _jwt_expires_seconds() -> int:
    raw = os.getenv("JWT_EXPIRES_SECONDS", "28800").strip()
    try:
        return max(60, int(raw))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="JWT_EXPIRES_SECONDS must be an integer") from exc


def mint_access_token(*, sub: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + _jwt_expires_seconds(),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def parse_bearer_token(authorization: str | None) -> Principal | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts[0].strip().lower(), parts[1].strip()
    if scheme != "bearer" or not token:
        return None

    try:
        claims = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    sub = str(claims.get("sub") or "user")
    role = str(claims.get("role") or "user")
    if role not in {"user", "admin", "admin_readonly"}:
        role = "user"
    return Principal(role=role, actor=sub, sub=sub, method="jwt")


def resolve_principal(
    *,
    authorization: str | None,
    api_key: str | None,
) -> Principal:
    """Resolve caller identity from (1) Bearer JWT, else (2) X-API-Key, else (3) anonymous if allowed."""

    jwt_principal = parse_bearer_token(authorization)
    if jwt_principal is not None:
        return jwt_principal

    # API-key fallback: treat valid api keys as admin (dev/ops bootstrap compatibility).
    if api_key is not None:
        verify_api_key(api_key)
        actor = resolve_actor_name(api_key)
        sub = actor or "api_key"
        return Principal(role="admin", actor=actor, sub=sub, method="api_key")

    if _truthy_env("AUTH_ALLOW_ANONYMOUS", "false"):
        return Principal(role="user", actor="anonymous", sub="anonymous", method="anonymous")

    raise HTTPException(status_code=401, detail="Authentication required")


def assert_admin(principal: Principal, *, allow_readonly: bool = False) -> None:
    allowed = {"admin", "admin_readonly"} if allow_readonly else {"admin"}
    if principal.role not in allowed:
        # If caller is anonymous (no credentials), treat this as an auth failure (401),
        # not an authorization failure (403), to keep admin endpoints consistent.
        if principal.method == "anonymous":
            raise HTTPException(status_code=401, detail="Authentication required")
        raise HTTPException(status_code=403, detail="Admin permission required")


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self.calls = defaultdict(list)

    def allow(self, client_id: str) -> None:
        now = time.time()
        bucket = self.calls[client_id]
        while bucket and bucket[0] <= now - self.window:
            bucket.pop(0)
        if len(bucket) >= self.limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        bucket.append(now)


_rate_limiter: RateLimiter | None = None
_admin_keys: Dict[str, str] | None = None


def _load_admin_keys() -> Dict[str, str]:
    global _admin_keys
    if _admin_keys is not None:
        return _admin_keys
    mapping: Dict[str, str] = {}
    raw = os.getenv("ADMIN_API_KEYS")
    if raw:
        pairs = [entry.strip() for entry in raw.split(",") if entry.strip()]
        for pair in pairs:
            if ":" in pair:
                name, key = pair.split(":", 1)
                mapping[key.strip()] = name.strip()
            else:
                mapping[pair] = pair
    _admin_keys = mapping
    return _admin_keys


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        limit = int(os.getenv("API_RATE_LIMIT", "60"))
        window = int(os.getenv("API_RATE_WINDOW", "60"))
        _rate_limiter = RateLimiter(limit=limit, window_seconds=window)
    return _rate_limiter


def resolve_actor_name(api_key: str | None) -> str:
    valid_keys = _load_admin_keys()
    if valid_keys and api_key in valid_keys:
        return valid_keys[api_key]

    expected_default = os.getenv("API_AUTH_TOKEN")
    if expected_default and api_key == expected_default:
        return "default"

    if api_key is None:
        return "anonymous"

    if valid_keys:
        return "unknown"

    return "anonymous"
