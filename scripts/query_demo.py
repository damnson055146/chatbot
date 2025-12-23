"""Demo script to query the RAG API with bilingual slot guidance."""
from __future__ import annotations

import json
import uuid
from typing import Optional

import requests

API_URL = "http://localhost:8000"
API_KEY = "secret"  # replace with configured API key


def _post(path: str, payload: dict, *, lang: Optional[str] = None) -> dict:
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }
    if lang:
        headers["Accept-Language"] = lang
    response = requests.post(f"{API_URL}{path}", json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def query(question: str, *, language: str, session_id: Optional[str] = None, slots: Optional[dict] = None) -> dict:
    payload = {
        "question": question,
        "language": language,
        "session_id": session_id,
        "slots": slots or {},
        "top_k": 4,
        "k_cite": 2,
    }
    return _post("/v1/query", payload, lang=language)


def main() -> None:
    print("--- First round (ZH) ---")
    resp = query("申请英国留学需要准备哪些材料？", language="zh")
    print(json.dumps(resp["slot_prompts"], ensure_ascii=False, indent=2))
    print(json.dumps(resp["slot_suggestions"], ensure_ascii=False, indent=2))
    session_id = resp["session_id"]

    print("
--- Fill target country and continue (EN) ---")
    follow_up = query(
        "What documents are required for student visa?",
        language="en",
        session_id=session_id,
        slots={"target_country": "United Kingdom"},
    )
    print(json.dumps({
        "answer": follow_up["answer"],
        "slots": follow_up["slots"],
        "missing_slots": follow_up["missing_slots"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
