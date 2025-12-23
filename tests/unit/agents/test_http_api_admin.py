from datetime import datetime, UTC
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.agents import http_api
from src.utils import security, storage


@pytest.fixture(autouse=True)
def configure_auth(monkeypatch):
    monkeypatch.setenv("API_AUTH_TOKEN", "secret")
    monkeypatch.setenv("API_RATE_LIMIT", "100")
    monkeypatch.setenv("API_RATE_WINDOW", "60")
    security._rate_limiter = security.RateLimiter(limit=100, window_seconds=60)


def test_admin_config_falls_back_to_jobs(monkeypatch):
    monkeypatch.setattr(storage, "load_manifest", lambda: [])
    job_entry = {
        "job_type": "ingest",
        "doc_id": "visa_requirements",
        "metadata": {
            "source_name": "visa_requirements",
            "language": "en",
            "domain": "visa",
            "freshness": "2025-01-01",
            "url": "https://example.edu/visa",
            "tags": ["policy"],
            "description": "Visa requirements summary",
        },
    }
    monkeypatch.setattr(storage, "load_jobs_history", lambda limit=None: [job_entry])

    client = TestClient(http_api.app)
    response = client.get("/v1/admin/config", headers={"X-API-Key": "secret"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"], "expected fallback sources from job history"
    source = payload["sources"][0]
    assert source["doc_id"] == "visa_requirements"
    assert source["language"] == "en"
    assert source["domain"] == "visa"
    assert source["tags"] == ["policy"]



def test_admin_update_slots_supports_prompt_zh(monkeypatch):
    recorded = {}

    def fake_save(payload):
        recorded['payload'] = payload
        return Path('dummy.json')

    monkeypatch.setattr(storage, 'save_slots_config', fake_save)
    monkeypatch.setattr(http_api, 'save_slots_config', fake_save)
    monkeypatch.setattr(storage, 'load_slots_config', lambda: [])

    from src.schemas import slots as slots_module
    monkeypatch.setattr(slots_module, "_SLOTS_LOADED_FROM_STORAGE", False, raising=False)
    monkeypatch.setattr(slots_module, "_SLOT_DEFINITIONS", list(slots_module.DEFAULT_SLOT_DEFINITIONS), raising=False)

    client = TestClient(http_api.app)
    body = {
        'slots': [
            {
                'name': 'target_country',
                'description': 'Destination country',
                'prompt': 'Which country?',
                'prompt_zh': '你计划申请哪个国家？',
                'required': True,
                'value_type': 'string',
            }
        ]
    }
    response = client.post('/v1/admin/slots', headers={'X-API-Key': 'secret'}, json=body)
    assert response.status_code == 200
    data = response.json()
    assert data['slots'][0]['prompt_zh'] == '你计划申请哪个国家？'
    assert recorded['payload'][0]['prompt_zh'] == '你计划申请哪个国家？'
    slots_module.update_slot_definitions(list(slots_module.DEFAULT_SLOT_DEFINITIONS))
    slots_module._SLOTS_LOADED_FROM_STORAGE = False
