from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Callable, Dict

from fastapi import HTTPException


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
