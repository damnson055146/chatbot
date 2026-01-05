from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class SlotDefinition:
    name: str
    description: str
    required: bool = False
    prompt: str | None = None
    prompt_zh: str | None = None
    value_type: str = "string"
    choices: List[str] | None = None
    min_value: float | None = None
    max_value: float | None = None


DEFAULT_SLOT_DEFINITIONS: List[SlotDefinition] = [
    SlotDefinition(
        name="student_name",
        description="Preferred name so the assistant can address the student personally",
        required=True,
        prompt="May I have the name you'd like me to use when addressing you?",
        prompt_zh="我该如何称呼你？",
    ),
    SlotDefinition(
        name="contact_email",
        description="Email address for sending follow-up materials",
        prompt="Where can I email follow-up checklists or resources?",
        prompt_zh="如果需要后续发送材料，请提供一个邮箱。",
    ),
    SlotDefinition(
        name="target_country",
        description="Destination country for the study-abroad plan",
        required=True,
        prompt="Which country are you hoping to study in?",
        prompt_zh="你计划申请哪个国家？",
    ),
    SlotDefinition(
        name="degree_level",
        description="Degree level (e.g., undergraduate, postgraduate)",
        prompt="What degree level are you working toward (e.g., undergraduate, postgraduate)?",
        prompt_zh="你计划申请什么学历层级（如本科、硕士）？",
    ),
    SlotDefinition(
        name="discipline",
        description="Intended major or field of study",
        prompt="Which major or discipline are you most interested in exploring?",
        prompt_zh="你最想申请的专业或方向是什么？",
    ),
    SlotDefinition(
        name="gpa",
        description="Current GPA or equivalent academic score",
        prompt="What is your latest GPA or average score?",
        prompt_zh="你目前的平均成绩/GPA 是多少？",
        value_type="number",
        min_value=0.0,
        max_value=4.0,
    ),
    SlotDefinition(
        name="ielts",
        description="IELTS overall score (or other English test score)",
        prompt="What is your IELTS (or equivalent) score?",
        prompt_zh="你的雅思或其他英语成绩是多少？",
        value_type="number",
        min_value=0.0,
        max_value=9.0,
    ),
    SlotDefinition(
        name="budget",
        description="Approximate annual budget in local currency",
        prompt="What is your annual budget for study abroad?",
        prompt_zh="你的留学预算（每年）是多少？",
        value_type="number",
        min_value=0.0,
    ),
    SlotDefinition(
        name="timeframe",
        description="Target intake or start date (e.g., 2025 Fall)",
        prompt="When do you plan to start your studies?",
        prompt_zh="你打算什么时候开始留学？",
    ),
    SlotDefinition(
        name="current_stage",
        description="Where the student is in the application journey (researching, applying, admitted, etc.)",
        prompt="Which stage are you currently in (researching schools, preparing documents, already applying)?",
        prompt_zh="你目前处于哪个阶段（如了解项目、准备材料、已经在申请）？",
    ),
    SlotDefinition(
        name="priority_concern",
        description="Top concern or blocker the student wants help with",
        prompt="What is the biggest concern you'd like me to focus on?",
        prompt_zh="你现在最希望我帮你解决的核心问题是什么？",
    ),
]

_SLOT_DEFINITIONS: List[SlotDefinition] = list(DEFAULT_SLOT_DEFINITIONS)
_SLOTS_LOADED_FROM_STORAGE = False


def _ensure_loaded_from_storage() -> None:
    global _SLOT_DEFINITIONS, _SLOTS_LOADED_FROM_STORAGE
    if _SLOTS_LOADED_FROM_STORAGE:
        return
    try:
        from src.utils.storage import load_slots_config
    except Exception:  # pragma: no cover - optional dependency during import
        _SLOTS_LOADED_FROM_STORAGE = True
        return

    records = load_slots_config()
    if records:
        base = {slot.name: slot for slot in DEFAULT_SLOT_DEFINITIONS}
        for record in records:
            definition = _slot_from_dict(record)
            if definition:
                base[definition.name] = definition
        _SLOT_DEFINITIONS = list(base.values())
    _SLOTS_LOADED_FROM_STORAGE = True


def _slot_from_dict(data: Dict[str, Any]) -> Optional[SlotDefinition]:
    name = normalize_slot_name(str(data.get("name", "")))
    if not name:
        return None
    description = str(data.get("description", ""))
    prompt = data.get("prompt")
    prompt_zh = data.get("prompt_zh")
    required = bool(data.get("required", False))
    value_type = str(data.get("value_type", "string"))
    choices = data.get("choices")
    if choices is not None:
        choices = [str(choice) for choice in choices]
    min_value = data.get("min_value")
    max_value = data.get("max_value")
    try:
        min_val = float(min_value) if min_value is not None else None
    except (TypeError, ValueError):  # pragma: no cover - guard invalid config
        min_val = None
    try:
        max_val = float(max_value) if max_value is not None else None
    except (TypeError, ValueError):  # pragma: no cover - guard invalid config
        max_val = None

    return SlotDefinition(
        name=name,
        description=description,
        required=required,
        prompt=prompt,
        prompt_zh=prompt_zh,
        value_type=value_type,
        choices=choices,
        min_value=min_val,
        max_value=max_val,
    )


def _allowed_slot_names() -> set[str]:
    _ensure_loaded_from_storage()
    return {slot.name for slot in _SLOT_DEFINITIONS}


def get_slot_definition(name: str) -> SlotDefinition | None:
    _ensure_loaded_from_storage()
    normalized = normalize_slot_name(name)
    for slot in _SLOT_DEFINITIONS:
        if slot.name == normalized:
            return slot
    return None


def normalize_slot_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def filter_valid_slots(slots: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_loaded_from_storage()
    cleaned: Dict[str, Any] = {}
    for key, value in slots.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        slot_key = normalize_slot_name(key)
        if slot_key in _allowed_slot_names():
            cleaned[slot_key] = value
    return cleaned


def missing_required_slots(slots: Dict[str, Any]) -> List[SlotDefinition]:
    _ensure_loaded_from_storage()
    filtered = filter_valid_slots(slots)
    missing: List[SlotDefinition] = []
    for slot in _SLOT_DEFINITIONS:
        if slot.required and slot.name not in filtered:
            missing.append(slot)
    return missing


def slot_definitions() -> Iterable[SlotDefinition]:
    _ensure_loaded_from_storage()
    return list(_SLOT_DEFINITIONS)


def validate_slot_value(slot: SlotDefinition, value: Any) -> str | None:
    if value is None:
        return "required" if slot.required else None

    if slot.value_type == "number":
        try:
            number_value = float(value)
        except (TypeError, ValueError):
            return "must be a number"
        if slot.min_value is not None and number_value < slot.min_value:
            return f"must be ≥ {slot.min_value}"
        if slot.max_value is not None and number_value > slot.max_value:
            return f"must be ≤ {slot.max_value}"
        return None

    if slot.value_type == "choice":
        if not slot.choices:
            return None
        if str(value) not in slot.choices:
            return "invalid choice"
        return None

    # string fallback
    if isinstance(value, str) and value.strip():
        return None
    return "required" if slot.required else None


def validate_slots(slots: Dict[str, Any]) -> Dict[str, str]:
    _ensure_loaded_from_storage()
    errors: Dict[str, str] = {}
    for name, value in slots.items():
        definition = get_slot_definition(name)
        if not definition:
            continue
        error = validate_slot_value(definition, value)
        if error:
            errors[definition.name] = error
    return errors


def update_slot_definitions(updated_slots: List[SlotDefinition]) -> None:
    global _SLOT_DEFINITIONS
    _SLOT_DEFINITIONS = updated_slots
    _allowed_slot_names()
    global _SLOTS_LOADED_FROM_STORAGE
    _SLOTS_LOADED_FROM_STORAGE = True






def list_slots(language: str | None = None) -> List[Dict[str, Any]]:
    _ensure_loaded_from_storage()
    lang = (language or "en").lower()
    slots_payload: List[Dict[str, Any]] = []
    for slot in _SLOT_DEFINITIONS:
        prompt = get_slot_prompt(slot.name, lang)
        entry = {
            "name": slot.name,
            "description": slot.description,
            "required": slot.required,
            "value_type": slot.value_type,
            "prompt": prompt,
            "prompt_zh": slot.prompt_zh,
            "choices": slot.choices,
            "min_value": slot.min_value,
            "max_value": slot.max_value,
        }
        slots_payload.append(entry)
    return slots_payload
def get_slot_prompt(name: str, language: str | None = None) -> str:
    definition = get_slot_definition(name)
    if not definition:
        return ""
    lang = (language or "en").lower()
    if lang.startswith("zh") and definition.prompt_zh:
        return definition.prompt_zh
    if definition.prompt:
        return definition.prompt
    if definition.prompt_zh:
        return definition.prompt_zh
    return definition.description or definition.name

def serialize_slots(definitions: Iterable[SlotDefinition]) -> List[Dict[str, Any]]:
    return [
        {
            "name": slot.name,
            "description": slot.description,
            "prompt": slot.prompt,
            "prompt_zh": slot.prompt_zh,
            "required": slot.required,
            "value_type": slot.value_type,
            "choices": slot.choices,
            "min_value": slot.min_value,
            "max_value": slot.max_value,
        }
        for slot in definitions
    ]
