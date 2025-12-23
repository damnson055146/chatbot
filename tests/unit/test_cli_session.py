import argparse

import pytest

from src.cli import cmd_session
from src.utils import session as session_module
from src.utils.session import SessionStore


def make_args(**kwargs):
    defaults = {"list": False, "session_id": None, "clear": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@pytest.fixture
def store(monkeypatch):
    store = SessionStore(ttl_seconds=3600)
    monkeypatch.setattr(session_module, "_SESSION_STORE", store)
    return store


def test_cmd_session_list_empty(store, capsys):
    cmd_session(make_args(list=True), {})
    out = capsys.readouterr().out
    assert "No active sessions." in out


def test_cmd_session_inspect(store, capsys):
    state = store.upsert(session_id=None, language="en", slot_updates={"target_country": "JP"})
    cmd_session(make_args(session_id=state.session_id), {})
    inspect_out = capsys.readouterr().out
    assert state.session_id in inspect_out
    assert "target_country" in inspect_out
    assert "TTL remaining:" in inspect_out
    assert "Slot count: 1" in inspect_out

    cmd_session(make_args(list=True), {})
    list_out = capsys.readouterr().out
    assert "slots=1" in list_out
    assert "ttl=" in list_out


def test_cmd_session_clear(store, capsys):
    state = store.upsert(session_id=None, language="en", slot_updates={"target_country": "CA"})
    cmd_session(make_args(session_id=state.session_id, clear=True), {})
    out = capsys.readouterr().out
    assert "Cleared session" in out
    assert store.get(state.session_id) is None
