from __future__ import annotations

OPENING_DEFAULTS: dict[str, str] = {
    "en": (
        "I keep up with visa, admissions, and scholarship updates so the process feels less overwhelming. "
        "Tell me where you are in the journey and I will help map the next step."
    ),
    "zh": "我会持续关注签证、申请和奖学金的动态，让流程没那么焦虑。告诉我你现在的阶段，我来陪你一起理清下一步。",
}


def opening_default_for(language: str) -> str:
    key = "zh" if language.lower().startswith("zh") else "en"
    return OPENING_DEFAULTS.get(key, OPENING_DEFAULTS["en"])


def opening_template_name(language: str) -> str:
    return "Assistant Opening (ZH)" if language.lower().startswith("zh") else "Assistant Opening (EN)"


def opening_template_description(language: str) -> str:
    return "Opening statement used on the chat landing screen, in the first assistant reply, and to guide overall tone."
