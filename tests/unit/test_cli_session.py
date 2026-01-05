import argparse

import pytest

from src.cli import cmd_session
from src.utils import conversation_store, storage
from src.utils.conversation_store import ConversationStore


def make_args(**kwargs):
    defaults = {"list": False, "session_id": None, "clear": False, "user_id": None}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture
def store(monkeypatch, tmp_path):
    processed = tmp_path / "processed"
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed)
    storage.ensure_dirs()
    store = ConversationStore()
    monkeypatch.setattr(conversation_store, "get_conversation_store", lambda: store)
    return store


def test_cmd_session_list_empty(store, capsys):
    cmd_session(make_args(list=True, user_id="test-user"), {})
    out = capsys.readouterr().out
    assert "No sessions." in out


def test_cmd_session_inspect(store, capsys):
    state = store.upsert_session(
        "test-user",
        session_id=None,
        language="en",
        slot_updates={"target_country": "JP"},
        reset_slots=[],
    )
    cmd_session(make_args(session_id=state.session_id, user_id="test-user"), {})
    inspect_out = capsys.readouterr().out
    assert state.session_id in inspect_out
    assert "target_country" in inspect_out
    assert "Slot count: 1" in inspect_out

    cmd_session(make_args(list=True, user_id="test-user"), {})
    list_out = capsys.readouterr().out
    assert "slots=1" in list_out


def test_cmd_session_clear(store, capsys):
    state = store.upsert_session(
        "test-user",
        session_id=None,
        language="en",
        slot_updates={"target_country": "CA"},
        reset_slots=[],
    )
    cmd_session(make_args(session_id=state.session_id, clear=True, user_id="test-user"), {})
    out = capsys.readouterr().out
    assert "Cleared session" in out
    assert store.get_session("test-user", state.session_id) is None
