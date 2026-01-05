from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
import asyncio
import re
import math
from urllib.parse import urlparse
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from dataclasses import dataclass
from typing import Any, Dict, List

from src.schemas.models import Citation, QueryDiagnostics, QueryRequest, QueryResponse
from src.schemas.slots import (
    filter_valid_slots,
    get_slot_prompt,
    missing_required_slots,
    slot_definitions,
)
from src.utils.index_manager import get_index_manager
from src.utils.logging import get_logger
from src.utils.observability import get_metrics
from src.utils.opening import get_assistant_opening
from src.utils.rerank import get_reranker
from src.utils.conversation_store import get_conversation_store
from src.utils.siliconflow import chat_stream, chat, chat_multimodal, chat_multimodal_stream
from src.utils.storage import (
    get_active_prompt,
    get_doc_lookup,
    load_assistant_profile,
    UPLOADS_DIR,
    load_upload_record,
    is_upload_expired,
)
from src.utils.prompt_catalog import render_prompt, resolve_fragment, normalize_assistant_prompt
from src.schemas.models import HighlightSpan
from src.utils.tracing import start_span
from src.utils.text_extract import extract_text_from_bytes

log = get_logger(__name__)


def _assistant_display_name() -> str:
    profile = load_assistant_profile()
    name = str(profile.get("name") or "").strip()
    return name or "Lumi"


def _default_system_prompt(language: str) -> str:
    assistant_name = _assistant_display_name()
    return resolve_fragment("system_prompt", language, {"assistant_name": assistant_name})


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


_ATTACHMENT_TEXT_MAX_CHARS = _read_int_env("ATTACHMENT_TEXT_MAX_CHARS", 4000)
_ATTACHMENT_IMAGE_MAX_BYTES = _read_int_env("ATTACHMENT_IMAGE_MAX_BYTES", 4 * 1024 * 1024)
_ATTACHMENT_RETENTION_DAYS = _read_int_env("UPLOAD_RETENTION_DAYS", 30)
SUMMARY_MAX_TURNS = 5
SUMMARY_MESSAGE_MAX_CHARS = _read_int_env("SUMMARY_MESSAGE_MAX_CHARS", 400)
SUMMARY_MAX_CHARS = _read_int_env("SUMMARY_MAX_CHARS", 1200)
SUMMARY_MAX_TOKENS = _read_int_env("SUMMARY_MAX_TOKENS", 280)


@dataclass(frozen=True)
class AttachmentContext:
    text: str
    images: List[str]


def _answer_language(req: QueryRequest, session_language: str | None = None) -> str:
    lang = (req.language or "auto").lower()
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("en"):
        return "en"
    if session_language in {"zh", "en"}:
        return session_language
    return "zh" if any("\u4e00" <= ch <= "\u9fff" for ch in req.question) else "en"


_SUGGESTION_TARGET_COUNT = 3
_SUGGESTION_MAX_CONTEXT_CHARS = 600
_SUGGESTION_MAX_ITEM_CHARS = 120
_SUGGESTION_BLOCKLIST_EN = (
    "please provide",
    "please share",
    "provide your",
    "your email",
    "your name",
    "please tell me",
)
_SUGGESTION_BLOCKLIST_ZH = (
    "请提供",
    "请补充",
    "请填写",
    "请告诉我",
    "你的邮箱",
    "你的姓名",
)


def _normalize_suggestion_item(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"^[\-\*\d\.\)\]、]+", "", cleaned).strip()
    cleaned = cleaned.strip('"').strip("'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _slot_context_summary(slots: Dict[str, Any], language: str) -> str:
    if not isinstance(slots, dict):
        return ""
    parts: List[str] = []

    def _add(key: str, en_label: str, zh_label: str) -> None:
        value = slots.get(key)
        if value is None:
            return
        if isinstance(value, str) and not value.strip():
            return
        label = zh_label if language == "zh" else en_label
        parts.append(f"{label}: {value}")

    _add("target_country", "Target country", "目标国家")
    _add("degree_level", "Degree level", "学历层级")
    _add("discipline", "Discipline", "目标专业")
    _add("timeframe", "Timeframe", "入学时间")
    _add("current_stage", "Current stage", "当前阶段")
    _add("priority_concern", "Priority concern", "核心关注")
    _add("budget", "Budget", "预算")
    _add("gpa", "GPA", "GPA")
    _add("ielts", "IELTS", "雅思/托福")
    summary = "; ".join(parts)
    return _truncate_text(summary, _SUGGESTION_MAX_CONTEXT_CHARS)


def _suggestion_prompt(
    *,
    language: str,
    question: str,
    answer: str,
    memory_summary: str | None,
    slots: Dict[str, Any],
) -> tuple[str, str]:
    slots_summary = _slot_context_summary(slots, language)
    question_block = _truncate_text(question.strip(), _SUGGESTION_MAX_CONTEXT_CHARS)
    answer_block = _truncate_text(answer.strip(), _SUGGESTION_MAX_CONTEXT_CHARS)
    summary_block = _truncate_text((memory_summary or "").strip(), _SUGGESTION_MAX_CONTEXT_CHARS)

    if language == "zh":
        system = "你负责生成学生可以向留学顾问追问的简短问题。只输出 JSON 数组。"
        prompt_lines = [
            "请基于上下文生成 3 条简短问题，供学生继续向留学顾问提问。",
            "要求：",
            "- 使用中文，学生视角发问，围绕当前话题。",
            "- 每条一句话，尽量不超过 30 个字。",
            "- 不要让学生提供个人信息，不要出现“请提供/请补充”等措辞。",
            "- 不要使用占位符（如 ____）。",
            "如果上下文不足以生成 3 条有用问题，请输出空数组 []。",
            "仅输出 JSON 数组，例如： [\"...\", \"...\", \"...\"]",
            f"用户问题：{question_block}",
        ]
        if answer_block:
            prompt_lines.append(f"助手答复要点：{answer_block}")
        if summary_block:
            prompt_lines.append(f"对话摘要：{summary_block}")
        if slots_summary:
            prompt_lines.append(f"已知信息：{slots_summary}")
        return "\n".join(prompt_lines), system

    system = "You generate short follow-up questions a student can ask a study-abroad counselor. Output JSON only."
    prompt_lines = [
        "Generate 3 short follow-up questions the student can ask next.",
        "Rules:",
        "- Use English, from the student's perspective, tied to the current topic.",
        "- One sentence each, preferably under 18 words.",
        "- Do not ask the student to provide personal info; avoid phrases like 'please provide'.",
        "- No placeholders like ____.",
        "If context is insufficient for 3 useful questions, output [] instead.",
        "Return only a JSON array, e.g., [\"...\", \"...\", \"...\"]",
        f"User question: {question_block}",
    ]
    if answer_block:
        prompt_lines.append(f"Assistant answer summary: {answer_block}")
    if summary_block:
        prompt_lines.append(f"Conversation summary: {summary_block}")
    if slots_summary:
        prompt_lines.append(f"Known profile: {slots_summary}")
    return "\n".join(prompt_lines), system


def _parse_suggestion_payload(raw: str, language: str) -> List[str]:
    cleaned = raw.strip()
    if not cleaned or cleaned.startswith("[offline]"):
        return []
    items: List[str] = []
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            data = data.get("suggestions")
        if isinstance(data, list):
            items = [item for item in data if isinstance(item, str)]
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                data = None
            if isinstance(data, list):
                items = [item for item in data if isinstance(item, str)]
        if not items:
            items = [line for line in cleaned.splitlines() if line.strip()]

    blocklist = _SUGGESTION_BLOCKLIST_ZH if language == "zh" else _SUGGESTION_BLOCKLIST_EN
    suggestions: List[str] = []
    seen: set[str] = set()
    for item in items:
        candidate = _normalize_suggestion_item(item)
        if not candidate:
            continue
        check = candidate if language == "zh" else candidate.lower()
        if any(term in check for term in blocklist):
            continue
        if "____" in candidate or "__" in candidate:
            continue
        if len(candidate) > _SUGGESTION_MAX_ITEM_CHARS:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        suggestions.append(candidate)
        if len(suggestions) >= _SUGGESTION_TARGET_COUNT:
            break
    if len(suggestions) != _SUGGESTION_TARGET_COUNT:
        return []
    return suggestions


async def _generate_followup_suggestions(
    *,
    language: str,
    question: str,
    answer: str,
    memory_summary: str | None,
    slots: Dict[str, Any],
) -> List[str]:
    if not question.strip():
        return []
    prompt, system = _suggestion_prompt(
        language=language,
        question=question,
        answer=answer,
        memory_summary=memory_summary,
        slots=slots,
    )
    try:
        raw = await chat(
            prompt,
            system_message=system,
            temperature=0.3,
            max_tokens=220,
        )
    except Exception as exc:
        log.warning("suggestions_generation_failed", error=str(exc))
        return []
    return _parse_suggestion_payload(raw, language)


_SLOT_EXTRACTION_MAX_MESSAGES = 6
_SLOT_EXTRACTION_MAX_MESSAGE_CHARS = 220


def _slot_extraction_dialogue(messages: List[Dict[str, Any]], language: str) -> str:
    if not messages:
        return ""
    labels = {"user": "用户", "assistant": "助手"} if language == "zh" else {"user": "User", "assistant": "Assistant"}
    lines: List[str] = []
    for message in messages[-_SLOT_EXTRACTION_MAX_MESSAGES :]:
        role = str(message.get("role") or "").lower()
        if role not in labels:
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        content = content.replace("\n", " ")
        content = _truncate_text(content, _SLOT_EXTRACTION_MAX_MESSAGE_CHARS)
        lines.append(f"{labels[role]}: {content}")
    return "\n".join(lines)


def _slot_target_names(existing_slots: Dict[str, Any] | None, request_slots: Dict[str, Any]) -> List[str]:
    existing = existing_slots or {}
    targets: List[str] = []
    for slot in slot_definitions():
        name = slot.name
        if not _slot_value_is_empty(request_slots.get(name)):
            continue
        if not _slot_value_is_empty(existing.get(name)):
            continue
        targets.append(name)
    return targets


def _slot_catalog_lines(language: str, target_names: List[str]) -> str:
    target_set = set(target_names)
    lines: List[str] = []
    for slot in slot_definitions():
        if slot.name not in target_set:
            continue
        prompt = get_slot_prompt(slot.name, language) or slot.description or slot.name
        lines.append(f"- {slot.name} ({slot.value_type}): {prompt}")
    return "\n".join(lines)


def _slot_known_summary(
    language: str,
    existing_slots: Dict[str, Any] | None,
    request_slots: Dict[str, Any],
) -> str:
    combined: Dict[str, Any] = {}
    if isinstance(existing_slots, dict):
        combined.update(existing_slots)
    combined.update(request_slots)
    return _slot_context_summary(combined, language)


def _slot_extraction_prompt(
    *,
    language: str,
    question: str,
    dialogue: str,
    memory_summary: str,
    known_slots: str,
    slot_lines: str,
) -> tuple[str, str]:
    question_block = _truncate_text(question.strip(), _SUGGESTION_MAX_CONTEXT_CHARS)
    summary_block = _truncate_text(memory_summary.strip(), _SUGGESTION_MAX_CONTEXT_CHARS)
    if language == "zh":
        system = "你是信息抽取助手，只输出 JSON 对象。"
        lines = [
            "从对话中抽取学生明确提到的槽位信息。",
            "要求：",
            "- 仅使用下列槽位名作为 key。",
            "- 未明确提到就不要输出该 key。",
            "- 数值保持为数字，邮箱保持原样。",
            "- 只输出 JSON 对象，例如 {\"target_country\":\"英国\"}。",
            f"可填写槽位：\n{slot_lines}",
            f"已知信息：{known_slots}" if known_slots else "已知信息：无",
        ]
        if summary_block:
            lines.append(f"对话摘要：{summary_block}")
        if dialogue:
            lines.append(f"历史对话：\n{dialogue}")
        lines.append(f"当前问题：{question_block}")
        return "\n".join(lines), system

    system = "You extract slot values from the conversation and output JSON only."
    lines = [
        "Extract the slot values explicitly stated by the student.",
        "Rules:",
        "- Use only the slot names listed below as keys.",
        "- Omit keys that are not explicitly mentioned.",
        "- Keep numbers as numbers, keep emails as-is.",
        "- Output JSON object only, e.g. {\"target_country\":\"UK\"}.",
        f"Slots:\n{slot_lines}",
        f"Known info: {known_slots}" if known_slots else "Known info: none",
    ]
    if summary_block:
        lines.append(f"Conversation summary: {summary_block}")
    if dialogue:
        lines.append(f"Recent dialogue:\n{dialogue}")
    lines.append(f"Current question: {question_block}")
    return "\n".join(lines), system


def _coerce_slot_value(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _parse_slot_extraction_payload(raw: str, target_names: List[str]) -> Dict[str, Any]:
    cleaned = raw.strip()
    if not cleaned or cleaned.startswith("[offline]"):
        return {}
    data: Any = None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                data = None
    if isinstance(data, dict) and isinstance(data.get("slots"), dict):
        data = data.get("slots")
    if not isinstance(data, dict):
        return {}
    candidates: Dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        coerced = _coerce_slot_value(value)
        if coerced is None:
            continue
        candidates[key] = coerced
    cleaned_slots = filter_valid_slots(candidates)
    if target_names:
        allowed = set(target_names)
        cleaned_slots = {key: value for key, value in cleaned_slots.items() if key in allowed}
    return cleaned_slots


async def _extract_slots_from_dialogue(
    *,
    language: str,
    question: str,
    messages: List[Dict[str, Any]],
    memory_summary: str,
    existing_slots: Dict[str, Any] | None,
    request_slots: Dict[str, Any],
    target_names: List[str],
) -> Dict[str, Any]:
    if not target_names or not question.strip():
        return {}
    slot_lines = _slot_catalog_lines(language, target_names)
    if not slot_lines:
        return {}
    dialogue = _slot_extraction_dialogue(messages, language)
    known_slots = _slot_known_summary(language, existing_slots, request_slots)
    prompt, system = _slot_extraction_prompt(
        language=language,
        question=question,
        dialogue=dialogue,
        memory_summary=memory_summary,
        known_slots=known_slots,
        slot_lines=slot_lines,
    )
    try:
        raw = await chat(
            prompt,
            system_message=system,
            temperature=0.0,
            max_tokens=200,
        )
    except Exception as exc:
        log.warning("slot_extraction_failed", error=str(exc))
        return {}
    return _parse_slot_extraction_payload(raw, target_names)


def _merge_extracted_slots(
    existing_slots: Dict[str, Any] | None,
    request_slots: Dict[str, Any],
    extracted_slots: Dict[str, Any],
) -> Dict[str, Any]:
    merged = dict(request_slots or {})
    existing = existing_slots or {}
    for key, value in extracted_slots.items():
        if key in merged and not _slot_value_is_empty(merged.get(key)):
            continue
        if not _slot_value_is_empty(existing.get(key)):
            continue
        merged[key] = value
    return merged


_NAME_STOP_WORDS_EN = {
    "student",
    "applicant",
    "applying",
    "apply",
    "studying",
    "study",
    "seeking",
}
_NAME_STOP_WORDS_ZH = {
    "学生",
    "同学",
    "留学",
    "申请",
    "本科",
    "硕士",
    "博士",
    "研究生",
}


def _extract_student_name(question: str) -> str | None:
    text = question.strip()
    if not text:
        return None
    patterns = [
        r"(?:my name is|i am|i'm|call me)\s+([A-Za-z][A-Za-z .'\-]{0,40})",
        r"(?:我是|我叫|叫我|我的名字是)\s*([^\s，。！？!?,;；:]{1,12})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        candidate = match.group(1).strip().strip("\"'()[]{}")
        candidate = re.split(r"[，。！？!?,;；:\n]", candidate)[0].strip()
        candidate = " ".join(candidate.split())
        if not candidate:
            continue
        if any(ch.isdigit() for ch in candidate):
            continue
        if len(candidate) < 2 or len(candidate) > 40:
            continue
        lower = candidate.lower()
        if any(word in lower for word in _NAME_STOP_WORDS_EN):
            continue
        if any(word in candidate for word in _NAME_STOP_WORDS_ZH):
            continue
        if len(candidate.split()) > 3:
            continue
        return candidate
    return None


def _truncate_text(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    return value[:limit].rstrip()


def _missing_slot_guidance(
    language: str,
    missing_names: List[str],
    slot_prompts: Dict[str, str],
) -> str:
    if not missing_names:
        return ""
    if language == "zh":
        prefix = "为继续提供协助，请补充以下信息："
    else:
        prefix = "To continue, please provide:"
    lines = [prefix]
    for name in missing_names:
        prompt = slot_prompts.get(name) or name
        lines.append(f"- {prompt}")
    return "\n\n" + "\n".join(lines)


def _slot_value_is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _merge_profile_slots(
    *,
    existing_slots: Dict[str, Any] | None,
    request_slots: Dict[str, Any] | None,
    profile_display_name: str | None,
    profile_contact_email: str | None,
) -> Dict[str, Any]:
    updates = dict(request_slots or {})
    defaults: Dict[str, Any] = {}
    if profile_display_name:
        defaults["student_name"] = profile_display_name
    if profile_contact_email:
        defaults["contact_email"] = profile_contact_email
    for key, value in defaults.items():
        if key in updates:
            continue
        if existing_slots and not _slot_value_is_empty(existing_slots.get(key)):
            continue
        updates[key] = value
    return updates


def _merge_question(question: str, attachment_text: str) -> str:
    if not attachment_text:
        return question
    merged = f"{question}\n\nAttachment notes:\n{attachment_text}"
    return _truncate_text(merged, _ATTACHMENT_TEXT_MAX_CHARS)


def _clean_summary_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    return cleaned.strip()


def _collect_recent_turns(
    messages: List[Dict[str, Any]],
    max_turns: int,
) -> List[tuple[str, str]]:
    turns: List[tuple[str, str]] = []
    idx = len(messages) - 1
    while idx >= 0 and len(turns) < max_turns:
        msg = messages[idx]
        if msg.get("role") == "assistant":
            assistant_text = _truncate_text(
                str(msg.get("content") or ""),
                SUMMARY_MESSAGE_MAX_CHARS,
            )
            if not assistant_text:
                idx -= 1
                continue
            j = idx - 1
            user_text = ""
            while j >= 0:
                candidate = messages[j]
                if candidate.get("role") == "user":
                    user_text = _truncate_text(
                        str(candidate.get("content") or ""),
                        SUMMARY_MESSAGE_MAX_CHARS,
                    )
                    break
                j -= 1
            if user_text:
                turns.append((user_text, assistant_text))
                idx = j - 1
                continue
        idx -= 1
    return list(reversed(turns))


def _summary_prompt(turns: List[tuple[str, str]], language: str) -> tuple[str, str]:
    lines: List[str] = []
    for idx, (user_text, assistant_text) in enumerate(turns, start=1):
        lines.append(
            f"Turn {idx}:\nUser: {user_text}\nAssistant: {assistant_text}"
        )
    conversation_block = "\n\n".join(lines)
    if language == "zh":
        system = "你是对话摘要助手，只保留客观事实，不要添加推测。"
        prompt = (
            "请基于以下最近对话生成简短摘要，最多 5 条，每条格式："
            "用户说了... chatbot回复了...。忽略引用编号和格式标记。"
            f"总字数不超过 {SUMMARY_MAX_CHARS} 字。\n\n"
            f"{conversation_block}"
        )
    else:
        system = "You summarize conversation turns for memory. Keep it factual and concise."
        prompt = (
            "Summarize the recent turns into up to 5 lines. Use the format: "
            "User said ...; Chatbot replied .... Ignore citations or formatting artifacts. "
            f"Keep the total length under {SUMMARY_MAX_CHARS} characters.\n\n"
            f"{conversation_block}"
        )
    return prompt, system


async def _summarize_recent_turns(turns: List[tuple[str, str]], language: str) -> str:
    if not turns:
        return ""
    prompt, system = _summary_prompt(turns, language)
    try:
        summary = await chat(
            prompt,
            system_message=system,
            temperature=0.1,
            max_tokens=SUMMARY_MAX_TOKENS,
        )
    except Exception as exc:
        log.warning("conversation_summary_failed", error=str(exc))
        return ""
    cleaned = _clean_summary_text(summary)
    if not cleaned or cleaned.startswith("[offline]"):
        return ""
    return _truncate_text(cleaned, SUMMARY_MAX_CHARS)


async def _refresh_conversation_summary(
    *,
    user_id: str,
    session_id: str,
    language: str,
    expected_last_message_id: str | None = None,
) -> None:
    store = get_conversation_store()
    messages = store.list_messages(user_id, session_id)
    if not messages:
        return
    if expected_last_message_id:
        last_id = str(messages[-1].get("id") or "")
        if last_id and last_id != expected_last_message_id:
            log.info(
                "conversation_summary_skipped",
                session_id=session_id,
                expected=expected_last_message_id,
                observed=last_id,
            )
            return
    turns = _collect_recent_turns(messages, SUMMARY_MAX_TURNS)
    summary = await _summarize_recent_turns(turns, language)
    if not summary:
        return
    store.update_session_summary(user_id, session_id, summary)


def _schedule_summary_refresh(
    *,
    user_id: str,
    session_id: str,
    language: str,
    last_message_id: str | None = None,
) -> None:
    try:
        asyncio.create_task(
            _refresh_conversation_summary(
                user_id=user_id,
                session_id=session_id,
                language=language,
                expected_last_message_id=last_message_id,
            )
        )
    except RuntimeError as exc:
        log.warning("conversation_summary_task_failed", error=str(exc), session_id=session_id)


def _load_attachment_context(upload_ids: List[str]) -> AttachmentContext:
    if not upload_ids:
        return AttachmentContext(text="", images=[])

    blocks: List[str] = []
    images: List[str] = []
    for upload_id in upload_ids:
        if not upload_id:
            continue
        record = load_upload_record(upload_id)
        if record is None:
            log.warning("attachment_missing", upload_id=upload_id)
            continue
        if record.purpose != "chat":
            log.warning("attachment_invalid_purpose", upload_id=upload_id, purpose=record.purpose)
            continue
        if is_upload_expired(record, default_retention_days=_ATTACHMENT_RETENTION_DAYS):
            log.warning("attachment_expired", upload_id=upload_id)
            continue
        upload_path = UPLOADS_DIR / record.storage_filename
        if not upload_path.exists():
            log.warning("attachment_file_missing", upload_id=upload_id)
            continue
        content = upload_path.read_bytes()
        try:
            extracted = extract_text_from_bytes(
                content=content,
                mime_type=record.mime_type,
                filename=record.filename,
            )
            if extracted.text:
                label = record.filename or upload_id
                blocks.append(f"{label}:\n{extracted.text}")
        except Exception as exc:
            log.warning("attachment_extract_failed", upload_id=upload_id, error=str(exc))

        if record.mime_type.startswith("image/"):
            if len(content) > _ATTACHMENT_IMAGE_MAX_BYTES:
                log.warning(
                    "attachment_image_too_large",
                    upload_id=upload_id,
                    size_bytes=len(content),
                    max_bytes=_ATTACHMENT_IMAGE_MAX_BYTES,
                )
                continue
            encoded = base64.b64encode(content).decode("ascii")
            images.append(f"data:{record.mime_type};base64,{encoded}")

    merged_text = _truncate_text("\n\n".join(blocks), _ATTACHMENT_TEXT_MAX_CHARS)
    return AttachmentContext(text=merged_text, images=images)


def _normalize_opening_text(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _opening_guidance(language: str, opening: str, is_first_reply: bool) -> str:
    if language == "zh":
        if is_first_reply:
            return (
                "本次为首次回复，请以以下开场白起句（可轻微改写但保留核心含义），并保持对话语气一致：\n"
                f"{opening}"
            )
        return f"后续回复保持与以下开场白一致的语气：\n{opening}"
    if is_first_reply:
        return (
            "For the first reply, start with the opening statement below (verbatim or lightly paraphrased) "
            "and keep the overall tone aligned with it:\n"
            f"{opening}"
        )
    return f"Keep the overall tone aligned with this opening statement:\n{opening}"


def _system_prompt(language: str, *, opening: str | None, is_first_reply: bool) -> str:
    record = get_active_prompt(language)
    if record:
        content = record.get("content")
        if content:
            prompt = normalize_assistant_prompt(str(content), _assistant_display_name(), language) or str(content)
        else:
            prompt = _default_system_prompt(language)
    else:
        prompt = _default_system_prompt(language)
    if not opening:
        return prompt
    cleaned_opening = opening.strip()
    if not cleaned_opening:
        return prompt
    guidance = _opening_guidance(language, cleaned_opening, is_first_reply)
    return f"{prompt}\n\n{guidance}"


def _apply_opening_prefix(answer: str, opening: str | None, is_first_reply: bool) -> str:
    if not is_first_reply or not opening:
        return answer
    cleaned_opening = opening.strip()
    if not cleaned_opening:
        return answer
    normalized_opening = _normalize_opening_text(cleaned_opening)
    normalized_answer = _normalize_opening_text(answer)
    if normalized_opening and normalized_opening in normalized_answer:
        return answer
    if not answer.strip():
        return cleaned_opening
    return f"{cleaned_opening}\n\n{answer}"


def _doc_last_verified_at(doc_meta) -> datetime | None:
    if not doc_meta:
        return None
    raw = getattr(doc_meta, "extra", {}) or {}
    verified_raw = raw.get("verified_at") if isinstance(raw, dict) else None
    if isinstance(verified_raw, str) and verified_raw:
        try:
            return datetime.fromisoformat(verified_raw)
        except Exception:
            return getattr(doc_meta, "updated_at", None)
    return getattr(doc_meta, "updated_at", None)


_PLACEHOLDER_SOURCE_URLS = {
    "https://example.com",
    "http://example.com",
    "https://example.com/",
    "http://example.com/",
    "https://www.example.com",
    "http://www.example.com",
    "https://www.example.com/",
    "http://www.example.com/",
}
_PLACEHOLDER_SOURCE_HOSTS = {
    "example.com",
    "www.example.com",
    "example.org",
    "www.example.org",
    "example.net",
    "www.example.net",
}


def _is_placeholder_source_url(raw_url: str | None) -> bool:
    if not raw_url:
        return True
    lowered = raw_url.strip().lower()
    if lowered in _PLACEHOLDER_SOURCE_URLS:
        return True
    if lowered.startswith("example."):
        return True
    parsed = urlparse(lowered)
    host = parsed.hostname or ""
    return host in _PLACEHOLDER_SOURCE_HOSTS


def _resolve_citation_url(doc_meta) -> str | None:
    if not doc_meta:
        return None
    raw_url = getattr(doc_meta, "url", None)
    extra = getattr(doc_meta, "extra", {}) or {}
    upload_id = extra.get("upload_id") if isinstance(extra, dict) else None
    if upload_id:
        record = load_upload_record(upload_id)
        if record:
            upload_url = f"/uploads/{record.storage_filename}"
            if _is_placeholder_source_url(raw_url):
                return upload_url
    return None if _is_placeholder_source_url(raw_url) else raw_url


_NUMERIC_PATTERN = re.compile(
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b\d+(?:[.,]\d+)?%?\b"
)
_STOPWORDS_EN = {
    "the",
    "and",
    "or",
    "for",
    "with",
    "that",
    "this",
    "are",
    "is",
    "to",
    "of",
    "in",
    "on",
    "by",
    "as",
    "at",
    "be",
    "an",
    "a",
}
_STOPWORDS_ZH = {"的", "了", "在", "是", "与", "和", "或", "对", "于", "为", "及"}
_DISCRETIONARY_TERMS_EN = (
    "may",
    "might",
    "can",
    "could",
    "normally",
    "usually",
    "typically",
    "generally",
    "at discretion",
    "case by case",
)
_DISCRETIONARY_TERMS_ZH = ("可能", "一般", "通常", "视情况", "酌情", "可视", "大多")


def _extract_numeric_tokens(text: str) -> set[str]:
    return {match.group(0) for match in _NUMERIC_PATTERN.finditer(text or "")}


def _keyword_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]+", text.lower())
    keywords = set()
    for token in tokens:
        if len(token) <= 1:
            continue
        if token in _STOPWORDS_EN or token in _STOPWORDS_ZH:
            continue
        keywords.add(token)
    return keywords


def _has_discretionary_language(text: str, language: str) -> bool:
    haystack = text.lower() if language == "en" else text
    terms = _DISCRETIONARY_TERMS_EN if language == "en" else _DISCRETIONARY_TERMS_ZH
    return any(term in haystack for term in terms)


def _detect_review_signal(passages: List[tuple[str, str]], language: str) -> tuple[bool, str | None]:
    if not passages:
        return False, None
    discretionary = any(_has_discretionary_language(text, language) for _, text in passages)
    for idx, (doc_id, text) in enumerate(passages):
        numbers = _extract_numeric_tokens(text)
        if not numbers:
            continue
        keywords = _keyword_tokens(text)
        for other_doc_id, other_text in passages[idx + 1 :]:
            if other_doc_id == doc_id:
                continue
            other_numbers = _extract_numeric_tokens(other_text)
            if not other_numbers or numbers == other_numbers:
                continue
            overlap = len(keywords & _keyword_tokens(other_text))
            if overlap >= 2:
                return True, "conflict"
    if discretionary:
        return True, "discretionary"
    return False, None


def _doc_recency_ts(doc_meta) -> float:
    verified = _doc_last_verified_at(doc_meta)
    return verified.timestamp() if verified else 0.0


def _apply_recency_tiebreak(items: List[Any], doc_lookup, *, epsilon: float = 0.02) -> List[Any]:
    if not items:
        return items
    bucket_size = epsilon if epsilon > 0 else 0.0

    def score_bucket(score: float) -> int:
        if bucket_size <= 0:
            return 0
        return math.floor(score / bucket_size)

    def recency_for(item: Any) -> float:
        doc_id = item.meta.get("doc_id") or item.chunk_id.split("-")[0]
        return _doc_recency_ts(doc_lookup.get(doc_id))

    return sorted(
        items,
        key=lambda item: (-score_bucket(float(item.score)), -recency_for(item), -float(item.score)),
    )


def _review_notice(language: str, reason: str | None) -> str:
    if language == "zh":
        if reason == "conflict":
            return "部分来源存在差异，我已保留相关引用供你核对。建议申请顾问复核后再做决定。"
        if reason == "discretionary":
            return "部分政策措辞带有弹性（如“通常”“可能”），我已保留相关引用供你核对。建议申请顾问复核。"
        return "相关信息存在不确定性，我已保留引用供核对，建议申请顾问复核。"
    if reason == "conflict":
        return "Some sources appear inconsistent. I have kept the citations so you can verify them; consider a counselor review."
    if reason == "discretionary":
        return "Some policies use discretionary language (for example, “normally” or “may”). I have kept the citations; consider a counselor review."
    return "Some information may be ambiguous. I have kept the citations for verification; consider a counselor review."


def _personalization_notes(language: str, slots: Dict[str, Any]) -> str:
    lines: List[str] = []

    def _text(en: str, zh: str) -> str:
        return zh if language == "zh" else en

    def _clean(value: Any) -> str:
        return str(value).strip()

    name = _clean(slots.get("student_name", "")) if isinstance(slots, dict) else ""
    if name:
        lines.append(
            _text(
                f"Address the student as {name} and keep the tone reassuring.",
                f"称呼学生为{name}，保持温和的语气。",
            )
        )

    stage = _clean(slots.get("current_stage", ""))
    if stage:
        lines.append(
            _text(
                f"They are currently at this stage: {stage}. Tailor the steps accordingly.",
                f"当前阶段：{stage}，请针对该阶段安排步骤。",
            )
        )

    priority = _clean(slots.get("priority_concern", ""))
    if priority:
        lines.append(
            _text(
                f"Primary concern to resolve first: {priority}.",
                f"需要优先解决的核心问题：{priority}。",
            )
        )

    country = _clean(slots.get("target_country", ""))
    if country:
        lines.append(
            _text(
                f"Their destination of interest is {country}; align policy references to this country.",
                f"目标国家为{country}，引用信息需围绕该国政策。",
            )
        )

    timeframe = _clean(slots.get("timeframe", ""))
    if timeframe:
        lines.append(
            _text(
                f"Requested intake/start timeline: {timeframe}.", f"目标入学时间：{timeframe}。"
            )
        )

    budget = slots.get("budget")
    if isinstance(budget, (int, float)) and budget > 0:
        lines.append(
            _text(
                f"Approximate annual budget: {budget}. Keep recommendations financially realistic.",
                f"每年预算约为 {budget}，建议需考虑费用可行性。",
            )
        )

    gpa = slots.get("gpa")
    if isinstance(gpa, (int, float)) and gpa > 0:
        lines.append(
            _text(
                f"Latest GPA/score: {gpa}. Use it when discussing competitiveness.",
                f"近期 GPA/成绩：{gpa}，可用于说明申请竞争力。",
            )
        )

    contact = _clean(slots.get("contact_email", ""))
    if contact:
        lines.append(
            _text(
                f"If sharing follow-up steps, mention that materials can be sent to {contact}.",
                f"若提及后续资料，可说明可发送至 {contact}。",
            )
        )

    if not lines:
        return _text("No personal details captured yet.", "暂无额外的学生画像信息。")
    return "\n".join(lines)


def _build_prompt(
    language: str,
    question: str,
    slots: Dict[str, Any],
    contexts: List[str],
    missing: List[str],
    memory_summary: str,
    opening: str | None,
    is_first_reply: bool,
    explain_like_new: bool,
    use_rag: bool,
) -> Dict[str, str]:
    assistant_name = _assistant_display_name()
    sys = _system_prompt(language, opening=opening, is_first_reply=is_first_reply)
    slot_lines = [f"{k}: {v}" for k, v in slots.items() if v]
    slot_section = "\n".join(slot_lines) if slot_lines else resolve_fragment("no_slots", language)
    if use_rag:
        context_section = "\n\n".join([f"[{i + 1}] {c}" for i, c in enumerate(contexts)]) or resolve_fragment(
            "no_context", language
        )
    else:
        context_section = resolve_fragment("rag_disabled_context", language)
    personalization_section = _personalization_notes(language, slots)

    if language == "zh":
        missing_value = "、".join(missing) if missing else resolve_fragment("missing_none", language)
    else:
        missing_value = ", ".join(missing) if missing else resolve_fragment("missing_none", language)

    memory_section = memory_summary.strip() if memory_summary else resolve_fragment("no_memory", language)

    extra_guidance = ""
    if explain_like_new:
        extra_guidance = f"\n\n{resolve_fragment('explain_like_new_hint', language)}"
    if not use_rag:
        extra_guidance = f"{extra_guidance}\n\n{resolve_fragment('rag_disabled_guidance', language)}"

    prompt = render_prompt(
        language,
        {
            "assistant_name": assistant_name,
            "system_prompt": sys,
            "personalization_section": personalization_section,
            "slot_section": slot_section,
            "missing_value": missing_value,
            "memory_section": memory_section,
            "question": question,
            "extra_guidance": extra_guidance,
            "context_section": context_section,
        },
    )
    return {"prompt": prompt, "system": sys}


async def answer_query(req: QueryRequest, *, user_id: str) -> QueryResponse:
    trace_id = uuid.uuid4().hex
    question_digest = hashlib.sha256(req.question.encode("utf-8")).hexdigest()[:16]
    question_length = len(req.question)
    request_language = (req.language or "auto").lower()

    store = get_conversation_store()
    existing = store.get_session(user_id, req.session_id) if req.session_id else None
    profile = store.get_profile(user_id)
    language = _answer_language(req, existing.language if existing else None)
    request_slots = dict(req.slots or {})
    if not request_slots.get("student_name"):
        extracted_name = _extract_student_name(req.question)
        if extracted_name:
            request_slots["student_name"] = extracted_name
    existing_slots = existing.slots if existing else None
    existing_messages: List[Dict[str, Any]] = []
    existing_summary = ""
    if existing and existing.session_id:
        existing_messages = store.list_messages(user_id, existing.session_id)
        existing_summary = store.get_session_summary(user_id, existing.session_id)
    target_names = _slot_target_names(existing_slots, request_slots)
    if target_names:
        extracted_slots = await _extract_slots_from_dialogue(
            language=language,
            question=req.question,
            messages=existing_messages,
            memory_summary=existing_summary,
            existing_slots=existing_slots,
            request_slots=request_slots,
            target_names=target_names,
        )
        if extracted_slots:
            request_slots = _merge_extracted_slots(existing_slots, request_slots, extracted_slots)
    slot_updates = _merge_profile_slots(
        existing_slots=existing_slots,
        request_slots=request_slots,
        profile_display_name=profile.display_name,
        profile_contact_email=profile.contact_email,
    )
    state = store.upsert_session(
        user_id,
        session_id=req.session_id,
        language=language,
        slot_updates=slot_updates,
        reset_slots=req.reset_slots,
    )
    language = state.language or language
    existing_messages = store.list_messages(user_id, state.session_id)
    is_first_user_message = not any(message.get("role") == "user" for message in existing_messages)
    opening = get_assistant_opening(language)
    attachment_context = _load_attachment_context(req.attachments)
    question_for_retrieval = _merge_question(req.question, attachment_context.text)
    memory_summary = store.get_session_summary(user_id, state.session_id)
    user_message = {
        "id": f"user-{uuid.uuid4().hex}",
        "role": "user",
        "content": req.question,
        "created_at": datetime.now(UTC).isoformat(),
        "language": language,
        "attachments": store.build_attachment_records(req.attachments),
    }
    store.append_message(user_id, state.session_id, user_message)

    base_span_attrs = {
        "trace_id": trace_id,
        "session_id": state.session_id,
        "question.length": question_length,
        "question.hash": question_digest,
        "request.language": request_language,
        "response.language": language,
        "attachments.count": len(req.attachments or []),
    }

    metrics = get_metrics()
    use_rag = req.use_rag
    retrieved: List[Any] = []
    reranked: List[Any] = []
    contexts: List[str] = []
    citations: List[Citation] = []
    review_passages: List[tuple[str, str]] = []
    review_suggested = False
    review_reason: str | None = None
    retrieval_ms = 0.0
    rerank_ms = 0.0

    if use_rag:
        index = get_index_manager()
        retrieval_attrs = dict(base_span_attrs)
        alpha_value = getattr(index, "alpha", 0.0)
        if alpha_value is None:
            alpha_value = 0.0
        retrieval_attrs.update(
            {
                "retrieval.top_k": req.top_k,
                "retrieval.k_cite": req.k_cite,
                "retrieval.alpha": float(alpha_value),
            }
        )
        with start_span("rag.retrieval", retrieval_attrs) as retrieval_span:
            start_retrieval = time.perf_counter()
            retrieved = index.query(question_for_retrieval, top_k=req.top_k)
            retrieval_ms = (time.perf_counter() - start_retrieval) * 1000
            if retrieval_span:
                retrieval_span.set_attribute("retrieval.duration_ms", retrieval_ms)
                retrieval_span.set_attribute("retrieval.result_count", len(retrieved))
                retrieval_span.set_attribute("retrieval.empty", 1 if not retrieved else 0)
        metrics.record_phase("retrieval", retrieval_ms)

    missing_defs = missing_required_slots(state.slots)
    missing_names = [slot.name for slot in missing_defs]
    slot_prompts = {name: get_slot_prompt(name, language) for name in missing_names}
    should_prompt_name = is_first_user_message and "student_name" in missing_names

    if use_rag and not retrieved:
        log.warning("no_chunks_available", trace_id=trace_id)
        metrics.record_empty_retrieval()
        metrics.record_phase("end_to_end", retrieval_ms)
        metrics.record("/v1/query", retrieval_ms)
        answer_text = "Corpus not indexed yet. Please ingest documents."
        if should_prompt_name:
            name_prompt = get_slot_prompt("student_name", language)
            if name_prompt and name_prompt.lower() not in answer_text.lower():
                answer_text = f"{answer_text}\n\n{name_prompt}"
        answer_text = _apply_opening_prefix(answer_text, opening, is_first_user_message)
        base_answer = answer_text
        guidance_block = _missing_slot_guidance(language, missing_names, slot_prompts)
        if guidance_block:
            answer_text = f"{answer_text}{guidance_block}"
        slot_suggestions = await _generate_followup_suggestions(
            language=language,
            question=req.question,
            answer=base_answer,
            memory_summary=memory_summary,
            slots=state.slots,
        )
        assistant_message = {
            "id": f"assistant-{uuid.uuid4().hex}",
            "role": "assistant",
            "content": answer_text,
            "created_at": datetime.now(UTC).isoformat(),
            "language": language,
            "citations": [],
            "diagnostics": None,
            "low_confidence": None,
            "attachments": [],
        }
        store.append_message(user_id, state.session_id, assistant_message)
        _schedule_summary_refresh(
            user_id=user_id,
            session_id=state.session_id,
            language=language,
            last_message_id=assistant_message["id"],
        )
        return QueryResponse(
            answer=answer_text,
            citations=[],
            trace_id=trace_id,
            session_id=state.session_id,
            slots=state.slots,
            slot_errors=state.slot_errors,
            missing_slots=missing_names,
            slot_prompts=slot_prompts,
            slot_suggestions=slot_suggestions,
        )

    if use_rag:
        reranker = get_reranker()
        rerank_attrs = dict(base_span_attrs)
        rerank_attrs.update(
            {
                "retrieval.result_count": len(retrieved),
                "rerank.k_cite": req.k_cite,
            }
        )
        with start_span("rag.rerank", rerank_attrs) as rerank_span:
            start_rerank = time.perf_counter()
            reranked = await reranker.rerank(
                question_for_retrieval,
                retrieved,
                trace_id=trace_id,
                language=language,
            )
            rerank_ms = (time.perf_counter() - start_rerank) * 1000
            if rerank_span:
                rerank_span.set_attribute("rerank.duration_ms", rerank_ms)
                rerank_span.set_attribute("rerank.result_count", len(reranked))
                rerank_span.set_attribute("rerank.fallback", 1 if not reranked else 0)
        if not reranked:
            metrics.record_rerank_fallback()
        metrics.record_phase("rerank", rerank_ms)

        k_cite = min(req.k_cite, len(reranked))
        doc_lookup = get_doc_lookup()

        if reranked:
            reranked = _apply_recency_tiebreak(reranked, doc_lookup)

        for item in reranked[:k_cite]:
            doc_id = item.meta.get("doc_id") or item.chunk_id.split("-")[0]
            doc_meta = doc_lookup.get(doc_id)
            source_name = getattr(doc_meta, "source_name", doc_id)
            domain = getattr(doc_meta, "domain", None)
            url = _resolve_citation_url(doc_meta)
            start_idx = item.meta.get("start_idx")
            end_idx = item.meta.get("end_idx")
            last_verified_at = _doc_last_verified_at(doc_meta)
            header_domain = domain or "general"
            snippet = f"{source_name} | {header_domain}: {item.text}"
            contexts.append(snippet)
            review_passages.append((doc_id, item.text))
            citation_highlights = []
            if start_idx is not None and end_idx is not None:
                citation_highlights = [HighlightSpan(start=start_idx, end=end_idx)]
            citations.append(
                Citation(
                    chunk_id=item.chunk_id,
                    doc_id=doc_id,
                    snippet=item.text[:200],
                    score=float(item.score),
                    source_name=source_name,
                    url=url,
                    domain=domain,
                    start_char=start_idx,
                    end_char=end_idx,
                    last_verified_at=last_verified_at,
                    highlights=citation_highlights,
                )
            )

    review_suggested, review_reason = _detect_review_signal(review_passages, language)

    generation_kwargs = {
        "temperature": req.temperature if req.temperature is not None else 0.2,
        "top_p": req.top_p,
        "max_tokens": req.max_tokens,
        "stop": req.stop if req.stop else None,
        "model": req.model,
    }

    prompt_payload = _build_prompt(
        language,
        question_for_retrieval,
        state.slots,
        contexts,
        missing_names,
        memory_summary,
        opening,
        is_first_user_message,
        req.explain_like_new,
        use_rag,
    )
    stop_tokens = generation_kwargs.get("stop") or []
    generation_attrs = dict(base_span_attrs)
    target_citations = req.k_cite if use_rag else 0
    generation_attrs.update(
        {
            "retrieval.result_count": len(retrieved),
            "rerank.result_count": len(reranked),
            "generation.target_citations": target_citations,
            "generation.temperature": generation_kwargs["temperature"],
            "generation.model": generation_kwargs["model"] or "default",
            "generation.stop_count": len(stop_tokens),
            "generation.explain_like_new": 1 if req.explain_like_new else 0,
        }
    )
    if generation_kwargs["top_p"] is not None:
        generation_attrs["generation.top_p"] = generation_kwargs["top_p"]
    if generation_kwargs["max_tokens"] is not None:
        generation_attrs["generation.max_tokens"] = generation_kwargs["max_tokens"]
    with start_span("rag.generation", generation_attrs) as generation_span:
        start_generation = time.perf_counter()
        if attachment_context.images:
            try:
                answer_text = await chat_multimodal(
                    prompt_payload["prompt"],
                    system_message=prompt_payload["system"],
                    image_data_urls=attachment_context.images,
                    **generation_kwargs,
                )
            except Exception as exc:
                log.warning("multimodal_chat_failed", error=str(exc), trace_id=trace_id)
                answer_text = await chat(
                    prompt_payload["prompt"],
                    system_message=prompt_payload["system"],
                    **generation_kwargs,
                )
        else:
            answer_text = await chat(
                prompt_payload["prompt"],
                system_message=prompt_payload["system"],
                **generation_kwargs,
            )
        generation_ms = (time.perf_counter() - start_generation) * 1000
        if generation_span:
            generation_span.set_attribute("generation.duration_ms", generation_ms)
            generation_span.set_attribute("generation.citation_count", len(citations))
            generation_span.set_attribute("generation.missing_slots", len(missing_names))
            generation_span.set_attribute("generation.answer_length", len(answer_text))
    metrics.record_phase("generation", generation_ms)

    low_confidence = False
    missing_names_display: List[str] = missing_names
    base_answer = answer_text.strip()
    guidance_block = _missing_slot_guidance(language, missing_names, slot_prompts)
    if guidance_block:
        answer_text = f"{answer_text}{guidance_block}"

    if review_suggested:
        answer_text = f"{answer_text}\n\n{_review_notice(language, review_reason)}"

    slot_suggestions = await _generate_followup_suggestions(
        language=language,
        question=req.question,
        answer=base_answer,
        memory_summary=memory_summary,
        slots=state.slots,
    )

    citation_count = len(citations)
    citation_coverage = None
    if use_rag:
        coverage_target = max(req.k_cite, 1)
        metrics.record_citation_coverage(citation_count, coverage_target)
        citation_coverage = min(citation_count / coverage_target, 1.0)
        if citation_count < coverage_target:
            metrics.record_low_confidence()
            low_confidence = True

    end_to_end_ms = retrieval_ms + rerank_ms + generation_ms
    metrics.record_phase("end_to_end", end_to_end_ms)
    metrics.record("/v1/query", end_to_end_ms)

    diagnostics = {
        "retrieval_ms": retrieval_ms,
        "rerank_ms": rerank_ms,
        "generation_ms": generation_ms,
        "end_to_end_ms": end_to_end_ms,
        "low_confidence": low_confidence,
        "citation_coverage": citation_coverage,
        "review_suggested": review_suggested,
        "review_reason": review_reason,
    }

    assistant_message = {
        "id": f"assistant-{uuid.uuid4().hex}",
        "role": "assistant",
        "content": answer_text,
        "created_at": datetime.now(UTC).isoformat(),
        "language": language,
        "citations": [citation.model_dump(mode="json") for citation in citations],
        "diagnostics": diagnostics,
        "low_confidence": low_confidence,
        "attachments": [],
    }
    store.append_message(user_id, state.session_id, assistant_message)
    _schedule_summary_refresh(
        user_id=user_id,
        session_id=state.session_id,
        language=language,
        last_message_id=assistant_message["id"],
    )

    return QueryResponse(
        answer=answer_text,
        citations=citations,
        trace_id=trace_id,
        session_id=state.session_id,
        slots=state.slots,
        slot_errors=state.slot_errors,
        missing_slots=missing_names_display,
        slot_prompts=slot_prompts,
        slot_suggestions=slot_suggestions,
        diagnostics=QueryDiagnostics(**diagnostics),
        attachments=req.attachments,
    )


def _format_sse(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def answer_query_sse(request, req: QueryRequest, *, user_id: str) -> AsyncIterator[str]:
    """Server-Sent Events version of the query endpoint.

    Emits `citations`, `chunk`, `completed`, `error` events compatible with the frontend parser.
    """

    try:
        trace_id = uuid.uuid4().hex
        question_digest = hashlib.sha256(req.question.encode("utf-8")).hexdigest()[:16]
        question_length = len(req.question)
        request_language = (req.language or "auto").lower()

        store = get_conversation_store()
        existing = store.get_session(user_id, req.session_id) if req.session_id else None
        profile = store.get_profile(user_id)
        language = _answer_language(req, existing.language if existing else None)
        request_slots = dict(req.slots or {})
        if not request_slots.get("student_name"):
            extracted_name = _extract_student_name(req.question)
            if extracted_name:
                request_slots["student_name"] = extracted_name
        existing_slots = existing.slots if existing else None
        existing_messages: List[Dict[str, Any]] = []
        existing_summary = ""
        if existing and existing.session_id:
            existing_messages = store.list_messages(user_id, existing.session_id)
            existing_summary = store.get_session_summary(user_id, existing.session_id)
        target_names = _slot_target_names(existing_slots, request_slots)
        if target_names:
            extracted_slots = await _extract_slots_from_dialogue(
                language=language,
                question=req.question,
                messages=existing_messages,
                memory_summary=existing_summary,
                existing_slots=existing_slots,
                request_slots=request_slots,
                target_names=target_names,
            )
            if extracted_slots:
                request_slots = _merge_extracted_slots(existing_slots, request_slots, extracted_slots)
        slot_updates = _merge_profile_slots(
            existing_slots=existing_slots,
            request_slots=request_slots,
            profile_display_name=profile.display_name,
            profile_contact_email=profile.contact_email,
        )
        state = store.upsert_session(
            user_id,
            session_id=req.session_id,
            language=language,
            slot_updates=slot_updates,
            reset_slots=req.reset_slots,
        )
        language = state.language or language
        existing_messages = store.list_messages(user_id, state.session_id)
        is_first_user_message = not any(message.get("role") == "user" for message in existing_messages)
        opening = get_assistant_opening(language)
        attachment_context = _load_attachment_context(req.attachments)
        question_for_retrieval = _merge_question(req.question, attachment_context.text)
        memory_summary = store.get_session_summary(user_id, state.session_id)
        user_message = {
            "id": f"user-{uuid.uuid4().hex}",
            "role": "user",
            "content": req.question,
            "created_at": datetime.now(UTC).isoformat(),
            "language": language,
            "attachments": store.build_attachment_records(req.attachments),
        }
        store.append_message(user_id, state.session_id, user_message)

        base_span_attrs = {
            "trace_id": trace_id,
            "session_id": state.session_id,
            "question.length": question_length,
            "question.hash": question_digest,
            "request.language": request_language,
            "response.language": language,
            "attachments.count": len(req.attachments or []),
        }

        metrics = get_metrics()
        use_rag = req.use_rag
        retrieved: List[Any] = []
        reranked: List[Any] = []
        contexts: List[str] = []
        citations: List[Citation] = []
        review_passages: List[tuple[str, str]] = []
        review_suggested = False
        review_reason: str | None = None
        retrieval_ms = 0.0
        rerank_ms = 0.0

        if use_rag:
            index = get_index_manager()
            retrieval_attrs = dict(base_span_attrs)
            alpha_value = getattr(index, "alpha", 0.0) or 0.0
            retrieval_attrs.update(
                {
                    "retrieval.top_k": req.top_k,
                    "retrieval.k_cite": req.k_cite,
                    "retrieval.alpha": float(alpha_value),
                }
            )
            with start_span("rag.retrieval", retrieval_attrs) as retrieval_span:
                start_retrieval = time.perf_counter()
                retrieved = index.query(question_for_retrieval, top_k=req.top_k)
                retrieval_ms = (time.perf_counter() - start_retrieval) * 1000
                if retrieval_span:
                    retrieval_span.set_attribute("retrieval.duration_ms", retrieval_ms)
                    retrieval_span.set_attribute("retrieval.result_count", len(retrieved))
                    retrieval_span.set_attribute("retrieval.empty", 1 if not retrieved else 0)
            metrics.record_phase("retrieval", retrieval_ms)

        missing_defs = missing_required_slots(state.slots)
        missing_names = [slot.name for slot in missing_defs]
        slot_prompts = {name: get_slot_prompt(name, language) for name in missing_names}
        should_prompt_name = is_first_user_message and "student_name" in missing_names

        if use_rag and not retrieved:
            metrics.record_empty_retrieval()
            metrics.record_phase("end_to_end", retrieval_ms)
            metrics.record("/v1/query", retrieval_ms)
            answer_text = "Corpus not indexed yet. Please ingest documents."
            if should_prompt_name:
                name_prompt = get_slot_prompt("student_name", language)
                if name_prompt and name_prompt.lower() not in answer_text.lower():
                    answer_text = f"{answer_text}\n\n{name_prompt}"
            answer_text = _apply_opening_prefix(answer_text, opening, is_first_user_message)
            base_answer = answer_text
            guidance_block = _missing_slot_guidance(language, missing_names, slot_prompts)
            if guidance_block:
                answer_text = f"{answer_text}{guidance_block}"
            slot_suggestions = await _generate_followup_suggestions(
                language=language,
                question=req.question,
                answer=base_answer,
                memory_summary=memory_summary,
                slots=state.slots,
            )
            assistant_message = {
                "id": f"assistant-{uuid.uuid4().hex}",
                "role": "assistant",
                "content": answer_text,
                "created_at": datetime.now(UTC).isoformat(),
                "language": language,
                "citations": [],
                "diagnostics": None,
                "low_confidence": None,
                "attachments": [],
            }
            store.append_message(user_id, state.session_id, assistant_message)
            _schedule_summary_refresh(
                user_id=user_id,
                session_id=state.session_id,
                language=language,
                last_message_id=assistant_message["id"],
            )
            response = QueryResponse(
                answer=answer_text,
                citations=[],
                trace_id=trace_id,
                session_id=state.session_id,
                slots=state.slots,
                slot_errors=state.slot_errors,
                missing_slots=missing_names,
                slot_prompts=slot_prompts,
                slot_suggestions=slot_suggestions,
                attachments=req.attachments,
            )
            yield _format_sse(
                "completed",
                response.model_dump(mode="json"),
            )
            return

        if use_rag:
            reranker = get_reranker()
            rerank_attrs = dict(base_span_attrs)
            rerank_attrs.update(
                {
                    "retrieval.result_count": len(retrieved),
                    "rerank.k_cite": req.k_cite,
                }
            )
            with start_span("rag.rerank", rerank_attrs) as rerank_span:
                start_rerank = time.perf_counter()
                reranked = await reranker.rerank(
                    question_for_retrieval,
                    retrieved,
                    trace_id=trace_id,
                    language=language,
                )
                rerank_ms = (time.perf_counter() - start_rerank) * 1000
                if rerank_span:
                    rerank_span.set_attribute("rerank.duration_ms", rerank_ms)
                    rerank_span.set_attribute("rerank.result_count", len(reranked))
                    rerank_span.set_attribute("rerank.fallback", 1 if not reranked else 0)
            if not reranked:
                metrics.record_rerank_fallback()
            metrics.record_phase("rerank", rerank_ms)

            k_cite = min(req.k_cite, len(reranked))
            doc_lookup = get_doc_lookup()

            if reranked:
                reranked = _apply_recency_tiebreak(reranked, doc_lookup)

            for item in reranked[:k_cite]:
                doc_id = item.meta.get("doc_id") or item.chunk_id.split("-")[0]
                doc_meta = doc_lookup.get(doc_id)
                source_name = getattr(doc_meta, "source_name", doc_id)
                domain = getattr(doc_meta, "domain", None)
                url = _resolve_citation_url(doc_meta)
                start_idx = item.meta.get("start_idx")
                end_idx = item.meta.get("end_idx")
                last_verified_at = _doc_last_verified_at(doc_meta)
                header_domain = domain or "general"
                snippet = f"{source_name} | {header_domain}: {item.text}"
                contexts.append(snippet)
                review_passages.append((doc_id, item.text))
                citation_highlights = []
                if start_idx is not None and end_idx is not None:
                    citation_highlights = [HighlightSpan(start=start_idx, end=end_idx)]
                citations.append(
                    Citation(
                        chunk_id=item.chunk_id,
                        doc_id=doc_id,
                        snippet=item.text[:200],
                        score=float(item.score),
                        source_name=source_name,
                        url=url,
                        domain=domain,
                        start_char=start_idx,
                        end_char=end_idx,
                        last_verified_at=last_verified_at,
                        highlights=citation_highlights,
                    )
                )

        review_suggested, review_reason = _detect_review_signal(review_passages, language)

        # Emit citations early so the client can render context rail while streaming
        yield _format_sse(
            "citations",
            {
                "trace_id": trace_id,
                "session_id": state.session_id,
                "citations": [c.model_dump(mode="json") for c in citations],
                "slots": state.slots,
                "missing_slots": missing_names,
                "slot_prompts": slot_prompts,
                "slot_errors": state.slot_errors,
                "diagnostics": {
                    "retrieval_ms": retrieval_ms,
                    "rerank_ms": rerank_ms,
                    "review_suggested": review_suggested,
                    "review_reason": review_reason,
                },
            },
        )

        generation_kwargs = {
            "temperature": req.temperature if req.temperature is not None else 0.2,
            "top_p": req.top_p,
            "max_tokens": req.max_tokens,
            "stop": req.stop if req.stop else None,
            "model": req.model,
        }

        prompt_payload = _build_prompt(
            language,
            question_for_retrieval,
            state.slots,
            contexts,
            missing_names,
            memory_summary,
            opening,
            is_first_user_message,
            req.explain_like_new,
            use_rag,
        )
        stop_tokens = generation_kwargs.get("stop") or []
        generation_attrs = dict(base_span_attrs)
        target_citations = req.k_cite if use_rag else 0
        generation_attrs.update(
            {
                "retrieval.result_count": len(retrieved),
                "rerank.result_count": len(reranked),
                "generation.target_citations": target_citations,
                "generation.temperature": generation_kwargs["temperature"],
                "generation.model": generation_kwargs["model"] or "default",
                "generation.stop_count": len(stop_tokens),
                "generation.explain_like_new": 1 if req.explain_like_new else 0,
            }
        )
        if generation_kwargs["top_p"] is not None:
            generation_attrs["generation.top_p"] = generation_kwargs["top_p"]
        if generation_kwargs["max_tokens"] is not None:
            generation_attrs["generation.max_tokens"] = generation_kwargs["max_tokens"]

        answer_parts: List[str] = []
        with start_span("rag.generation", generation_attrs) as generation_span:
            start_generation = time.perf_counter()
            stream_gen: AsyncIterator[str] | None = None

            class _ClientDisconnected(Exception):
                pass

            async def _consume_stream(gen: AsyncIterator[str]) -> AsyncIterator[str]:
                async for delta in gen:
                    # Stop generating immediately when client disconnects (AbortController on frontend)
                    try:
                        if request is not None and await request.is_disconnected():
                            raise _ClientDisconnected()
                    except Exception:
                        pass
                    if not delta:
                        continue
                    answer_parts.append(delta)
                    yield _format_sse(
                        "chunk",
                        {"delta": delta, "session_id": state.session_id, "trace_id": trace_id},
                    )

            try:
                if attachment_context.images:
                    stream_gen = chat_multimodal_stream(
                        prompt_payload["prompt"],
                        system_message=prompt_payload["system"],
                        image_data_urls=attachment_context.images,
                        temperature=generation_kwargs["temperature"],
                        top_p=generation_kwargs["top_p"],
                        max_tokens=generation_kwargs["max_tokens"],
                        stop=generation_kwargs["stop"],
                        model=generation_kwargs["model"],
                    )
                    async for payload in _consume_stream(stream_gen):
                        yield payload
                else:
                    stream_gen = chat_stream(
                        prompt_payload["prompt"],
                        system_message=prompt_payload["system"],
                        temperature=generation_kwargs["temperature"],
                        top_p=generation_kwargs["top_p"],
                        max_tokens=generation_kwargs["max_tokens"],
                        stop=generation_kwargs["stop"],
                        model=generation_kwargs["model"],
                    )
                    async for payload in _consume_stream(stream_gen):
                        yield payload
            except _ClientDisconnected:
                return
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if not attachment_context.images:
                    raise
                log.warning("multimodal_stream_failed", error=str(exc), trace_id=trace_id)
                if stream_gen is not None:
                    try:
                        await stream_gen.aclose()
                    except Exception:
                        pass
                stream_gen = chat_stream(
                    prompt_payload["prompt"],
                    system_message=prompt_payload["system"],
                    temperature=generation_kwargs["temperature"],
                    top_p=generation_kwargs["top_p"],
                    max_tokens=generation_kwargs["max_tokens"],
                    stop=generation_kwargs["stop"],
                    model=generation_kwargs["model"],
                )
                async for payload in _consume_stream(stream_gen):
                    yield payload
            finally:
                if stream_gen is not None:
                    try:
                        await stream_gen.aclose()
                    except Exception:
                        pass
            generation_ms = (time.perf_counter() - start_generation) * 1000
            if generation_span:
                generation_span.set_attribute("generation.duration_ms", generation_ms)
                generation_span.set_attribute("generation.citation_count", len(citations))
                generation_span.set_attribute("generation.missing_slots", len(missing_names))
                generation_span.set_attribute("generation.answer_length", sum(len(p) for p in answer_parts))
        metrics.record_phase("generation", generation_ms)

        answer_text = "".join(answer_parts).strip()
        base_answer = answer_text
        guidance_block = _missing_slot_guidance(language, missing_names, slot_prompts)
        if guidance_block:
            answer_text = f"{answer_text}{guidance_block}"
            yield _format_sse(
                "chunk",
                {"delta": guidance_block, "session_id": state.session_id, "trace_id": trace_id},
            )

        if review_suggested:
            review_block = "\n\n" + _review_notice(language, review_reason)
            answer_text = f"{answer_text}{review_block}"
            yield _format_sse(
                "chunk",
                {"delta": review_block, "session_id": state.session_id, "trace_id": trace_id},
            )

        slot_suggestions = await _generate_followup_suggestions(
            language=language,
            question=req.question,
            answer=base_answer,
            memory_summary=memory_summary,
            slots=state.slots,
        )

        citation_count = len(citations)
        citation_coverage = None
        low_confidence = False
        if use_rag:
            coverage_target = max(req.k_cite, 1)
            metrics.record_citation_coverage(citation_count, coverage_target)
            citation_coverage = min(citation_count / coverage_target, 1.0)
            low_confidence = citation_count < coverage_target
            if low_confidence:
                metrics.record_low_confidence()

        end_to_end_ms = retrieval_ms + rerank_ms + generation_ms
        metrics.record_phase("end_to_end", end_to_end_ms)
        metrics.record("/v1/query", end_to_end_ms)

        diagnostics = QueryDiagnostics(
            retrieval_ms=retrieval_ms,
            rerank_ms=rerank_ms,
            generation_ms=generation_ms,
            end_to_end_ms=end_to_end_ms,
            low_confidence=low_confidence,
            citation_coverage=citation_coverage,
            review_suggested=review_suggested,
            review_reason=review_reason,
        )

        response = QueryResponse(
            answer=answer_text or "I was unable to craft a response with the provided information.",
            citations=citations,
            trace_id=trace_id,
            session_id=state.session_id,
            slots=state.slots,
            slot_errors=state.slot_errors,
            missing_slots=missing_names,
            slot_prompts=slot_prompts,
            slot_suggestions=slot_suggestions,
            diagnostics=diagnostics,
            attachments=req.attachments,
        )
        assistant_message = {
            "id": f"assistant-{uuid.uuid4().hex}",
            "role": "assistant",
            "content": response.answer,
            "created_at": datetime.now(UTC).isoformat(),
            "language": language,
            "citations": [citation.model_dump(mode="json") for citation in citations],
            "diagnostics": diagnostics.model_dump(mode="json"),
            "low_confidence": low_confidence,
            "attachments": [],
        }
        store.append_message(user_id, state.session_id, assistant_message)
        _schedule_summary_refresh(
            user_id=user_id,
            session_id=state.session_id,
            language=language,
            last_message_id=assistant_message["id"],
        )
        yield _format_sse("completed", response.model_dump(mode="json"))
    except Exception as exc:
        yield _format_sse("error", {"message": str(exc)})
