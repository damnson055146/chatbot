import os
import json

import pytest
from fastapi.testclient import TestClient

from src.agents.http_api import app
from src.utils import security


@pytest.mark.smoke
def test_query_streaming_sse(monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "secret")
    monkeypatch.setattr(security, "_rate_limiter", None)
    client = TestClient(app)

    headers = {"X-API-Key": "secret", "Accept": "text/event-stream"}
    payload = {"question": "What is needed for student visa?", "language": "en"}

    events = []
    with client.stream("POST", "/v1/query?stream=true", json=payload, headers=headers) as response:
        assert response.status_code == 200
        buffer = ""
        for line in response.iter_lines():
            if line is None:
                continue
            buffer += line + "\n"
            if buffer.endswith("\n\n"):
                block = buffer.strip()
                buffer = ""
                if not block:
                    continue
                name = ""
                data_lines = []
                for row in block.splitlines():
                    if row.startswith("event:"):
                        name = row.split(":", 1)[1].strip()
                    elif row.startswith("data:"):
                        data_lines.append(row.split(":", 1)[1].strip())
                data = "\n".join(data_lines)
                payload_obj = json.loads(data) if data else {}
                events.append((name, payload_obj))
                if name == "completed":
                    break

    event_names = [name for name, _ in events]
    assert "completed" in event_names
    # citations event is expected early; chunk events may be absent in some offline/small responses, but usually present.
    assert "citations" in event_names or "chunk" in event_names

    completed_payload = next(payload for name, payload in events if name == "completed")
    assert completed_payload.get("session_id")
    assert isinstance(completed_payload.get("answer"), str)



