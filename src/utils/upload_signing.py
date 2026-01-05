from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime

DEFAULT_SIGNED_URL_TTL_SECONDS = 900
MIN_SIGNED_URL_TTL_SECONDS = 60


@dataclass(frozen=True)
class SignedUploadUrl:
    url: str
    expires_at: datetime


def _signing_secret() -> bytes:
    secret = os.getenv("UPLOAD_SIGNING_SECRET", "").strip()
    if not secret:
        secret = os.getenv("JWT_SECRET", "").strip()
    if not secret:
        secret = "dev-upload-secret"
    return secret.encode("utf-8")


def _signed_ttl_seconds() -> int:
    raw = os.getenv("UPLOAD_SIGNED_URL_TTL_SECONDS", str(DEFAULT_SIGNED_URL_TTL_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_SIGNED_URL_TTL_SECONDS
    return max(MIN_SIGNED_URL_TTL_SECONDS, value)


def _normalize_disposition(disposition: str | None) -> str:
    value = (disposition or "attachment").strip().lower()
    if value not in {"attachment", "inline"}:
        return "attachment"
    return value


def _signature_payload(upload_id: str, exp: int, disposition: str) -> str:
    return f"{upload_id}:{exp}:{disposition}"


def sign_upload_url(
    upload_id: str,
    *,
    base_path: str,
    disposition: str = "attachment",
    expires_in: int | None = None,
) -> SignedUploadUrl:
    ttl_seconds = expires_in if expires_in is not None else _signed_ttl_seconds()
    ttl_seconds = max(MIN_SIGNED_URL_TTL_SECONDS, int(ttl_seconds))
    disposition = _normalize_disposition(disposition)
    exp = int(time.time()) + ttl_seconds
    payload = _signature_payload(upload_id, exp, disposition)
    sig = hmac.new(_signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{base_path}?exp={exp}&sig={sig}&disposition={disposition}"
    return SignedUploadUrl(url=url, expires_at=datetime.fromtimestamp(exp, tz=UTC))


def verify_upload_signature(
    upload_id: str,
    *,
    exp: int,
    sig: str,
    disposition: str,
) -> bool:
    now = int(time.time())
    if exp <= now:
        return False
    disposition = _normalize_disposition(disposition)
    payload = _signature_payload(upload_id, exp, disposition)
    expected = hmac.new(_signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)
