from __future__ import annotations

from src.utils.logging import get_logger
from src.utils.opening_defaults import (
    opening_default_for,
    opening_template_description,
    opening_template_name,
)
from src.utils.storage import get_template, upsert_template

log = get_logger(__name__)

ASSISTANT_OPENING_TEMPLATE_IDS = {
    "en": "assistant_opening_en",
    "zh": "assistant_opening_zh",
}


def coerce_opening_language(language: str | None, *, default: str | None = "en") -> str | None:
    raw = (language or "").strip().lower()
    if raw.startswith("zh"):
        return "zh"
    if raw.startswith("en"):
        return "en"
    return default


def assistant_opening_template_id(language: str | None) -> str:
    normalized = coerce_opening_language(language, default="en") or "en"
    return ASSISTANT_OPENING_TEMPLATE_IDS[normalized]


def ensure_assistant_opening_template(language: str | None) -> dict:
    normalized = coerce_opening_language(language, default="en") or "en"
    template_id = ASSISTANT_OPENING_TEMPLATE_IDS[normalized]
    record = get_template(template_id)
    if record:
        return record
    record = upsert_template(
        {
            "template_id": template_id,
            "name": opening_template_name(normalized),
            "language": normalized,
            "category": "assistant",
            "description": opening_template_description(normalized),
            "content": opening_default_for(normalized),
        }
    )
    log.info("assistant_opening_default_created", template_id=template_id, language=normalized)
    return record


def get_assistant_opening(language: str | None) -> str | None:
    record = ensure_assistant_opening_template(language)
    content = record.get("content")
    if content is None:
        return None
    opening = str(content).strip()
    return opening or None
