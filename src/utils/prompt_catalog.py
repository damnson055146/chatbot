from __future__ import annotations

"""Prompt catalog loader and renderer with bilingual segment enforcement."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from src.utils.logging import get_logger

log = get_logger(__name__)

PROMPT_CATALOG_PATH = Path("assets/prompts/templates/prompt_catalog.json")


@dataclass(frozen=True)
class PromptSegment:
    key: str
    template_en: str
    template_zh: str


@dataclass(frozen=True)
class PromptCatalog:
    segments: tuple[PromptSegment, ...]
    fragments: Dict[str, Dict[str, str]]


_PROMPT_CATALOG_CACHE: PromptCatalog | None = None
_PROMPT_CATALOG_MTIME: float | None = None


def _normalize_language(language: str | None) -> str:
    raw = (language or "en").strip().lower()
    return "zh" if raw.startswith("zh") else "en"


def _require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Prompt catalog {label} must be a string.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"Prompt catalog {label} cannot be empty.")
    return value


def _parse_segments(raw_segments: Any) -> tuple[PromptSegment, ...]:
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("Prompt catalog segments must be a non-empty list.")
    seen = set()
    parsed = []
    for idx, entry in enumerate(raw_segments):
        if not isinstance(entry, dict):
            raise ValueError(f"Prompt catalog segment {idx} must be an object.")
        key = _require_text(entry.get("key"), label=f"segment[{idx}].key")
        if key in seen:
            raise ValueError(f"Prompt catalog segment key '{key}' is duplicated.")
        seen.add(key)
        template_en = _require_text(entry.get("template_en"), label=f"segment[{key}].template_en")
        template_zh = _require_text(entry.get("template_zh"), label=f"segment[{key}].template_zh")
        parsed.append(PromptSegment(key=key, template_en=template_en, template_zh=template_zh))
    return tuple(parsed)


def _parse_fragments(raw_fragments: Any) -> Dict[str, Dict[str, str]]:
    if raw_fragments is None:
        return {}
    if not isinstance(raw_fragments, dict):
        raise ValueError("Prompt catalog fragments must be an object.")
    parsed: Dict[str, Dict[str, str]] = {}
    for key, value in raw_fragments.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Prompt catalog fragment keys must be non-empty strings.")
        if not isinstance(value, dict):
            raise ValueError(f"Prompt catalog fragment '{key}' must be an object.")
        en = _require_text(value.get("en"), label=f"fragment[{key}].en")
        zh = _require_text(value.get("zh"), label=f"fragment[{key}].zh")
        parsed[key] = {"en": en, "zh": zh}
    return parsed


def _load_catalog_payload() -> PromptCatalog:
    payload = json.loads(PROMPT_CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Prompt catalog must be a JSON object.")
    segments = _parse_segments(payload.get("segments"))
    fragments = _parse_fragments(payload.get("fragments"))
    return PromptCatalog(segments=segments, fragments=fragments)


def get_prompt_catalog() -> PromptCatalog:
    """Load and cache the prompt catalog, enforcing bilingual segments."""
    global _PROMPT_CATALOG_CACHE, _PROMPT_CATALOG_MTIME
    if not PROMPT_CATALOG_PATH.exists():
        raise FileNotFoundError(f"Prompt catalog is missing: {PROMPT_CATALOG_PATH}")
    mtime = PROMPT_CATALOG_PATH.stat().st_mtime
    if _PROMPT_CATALOG_CACHE is not None and _PROMPT_CATALOG_MTIME == mtime:
        return _PROMPT_CATALOG_CACHE
    catalog = _load_catalog_payload()
    _PROMPT_CATALOG_CACHE = catalog
    _PROMPT_CATALOG_MTIME = mtime
    log.info("prompt_catalog_loaded", path=str(PROMPT_CATALOG_PATH), segments=len(catalog.segments))
    return catalog


def resolve_fragment(key: str, language: str | None, context: Mapping[str, Any] | None = None) -> str:
    """Return a rendered prompt fragment for the requested language."""
    catalog = get_prompt_catalog()
    fragment = catalog.fragments.get(key)
    if not fragment:
        raise KeyError(f"Prompt catalog fragment '{key}' is missing.")
    lang = _normalize_language(language)
    template = fragment.get(lang) or fragment.get("en")
    value = template.format_map(context or {})
    return str(value)


_ASSISTANT_INTRO_EN = re.compile(r"(?i)^\s*You are\s+[^,\n]+,\s*")
_ASSISTANT_INTRO_ZH = re.compile(r"^\s*\u4f60\u662f[^\uff0c\n]+\uff0c\s*")


def strip_assistant_intro(content: str | None) -> tuple[str | None, bool]:
    if content is None:
        return None, False
    stripped = _ASSISTANT_INTRO_EN.sub("", content, count=1)
    if stripped != content:
        return stripped, True
    stripped = _ASSISTANT_INTRO_ZH.sub("", content, count=1)
    if stripped != content:
        return stripped, True
    return content, False


def apply_assistant_name(content: str | None, assistant_name: str | None) -> str | None:
    if content is None:
        return None
    name = str(assistant_name or "").strip()
    if not name:
        return content
    rendered = content.replace("{{assistant_name}}", name).replace("{assistant_name}", name)
    if rendered != content:
        return rendered
    try:
        fragment = get_prompt_catalog().fragments.get("system_prompt", {})
    except Exception:
        return content
    for template in fragment.values():
        if not isinstance(template, str) or "{assistant_name}" not in template:
            continue
        pattern = re.escape(template).replace("\\{assistant_name\\}", "(?P<assistant_name>.+?)")
        if re.fullmatch(pattern, content, flags=re.DOTALL):
            return template.format_map({"assistant_name": name})
    return content


def normalize_assistant_prompt(
    content: str | None, assistant_name: str | None, language: str | None
) -> str | None:
    if content is None:
        return None
    stripped, removed = strip_assistant_intro(content)
    if removed:
        name = str(assistant_name or "").strip()
        if name:
            prefix = f"You are {name}, " if _normalize_language(language) == "en" else f"\u4f60\u662f{name}\uff0c"
            return f"{prefix}{(stripped or '').lstrip()}"
        return stripped
    rendered = apply_assistant_name(content, assistant_name)
    name = str(assistant_name or "").strip()
    if name:
        lang = _normalize_language(language)
        cleaned = str(rendered or "").lstrip()
        if lang == "en":
            if not cleaned.lower().startswith("you are "):
                return f"You are {name}, {cleaned}"
        else:
            if not cleaned.startswith("\u4f60\u662f"):
                return f"\u4f60\u662f{name}\uff0c{cleaned}"
    return rendered


def render_prompt(language: str, context: Mapping[str, Any]) -> str:
    """Render the prompt by concatenating catalog segments in order."""
    catalog = get_prompt_catalog()
    lang = _normalize_language(language)
    rendered: list[str] = []
    for segment in catalog.segments:
        template = segment.template_zh if lang == "zh" else segment.template_en
        rendered.append(str(template.format_map(context)))
    return "\n\n".join(rendered)


def iter_prompt_segments() -> Iterable[PromptSegment]:
    """Yield prompt segments in concatenation order."""
    return get_prompt_catalog().segments
