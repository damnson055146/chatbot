"""Quick client demo for multi-language slot catalog."""
from __future__ import annotations

import json
from typing import Optional

import requests

API_URL = "http://localhost:8000"
API_KEY = "secret"  # replace with configured API key


def fetch_slots(language: Optional[str] = None) -> None:
    params = {"lang": language} if language else None
    headers = {"X-API-Key": API_KEY}
    response = requests.get(f"{API_URL}/v1/slots", params=params, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    print("--- English prompts ---")
    fetch_slots(language="en")

    print("
--- Chinese prompts ---")
    fetch_slots(language="zh")


if __name__ == "__main__":
    main()
