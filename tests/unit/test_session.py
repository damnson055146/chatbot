from datetime import timedelta

from src.utils.session import SessionStore


def test_session_store_create_and_merge():
    store = SessionStore(ttl_seconds=3600)
    state = store.upsert(session_id=None, language="en", slot_updates={"target_country": "UK"})
    assert state.session_id
    assert state.slots["target_country"] == "UK"
    assert state.slot_errors == {}

    updated = store.upsert(
        session_id=state.session_id,
        language="en",
        slot_updates={"ielts": "6.5"},
    )
    assert updated.session_id == state.session_id
    assert updated.slots["target_country"] == "UK"
    assert updated.slots["ielts"] == "6.5"
    assert updated.slot_errors == {}

    invalid = store.upsert(
        session_id=state.session_id,
        language="en",
        slot_updates={"gpa": "ten"},
    )
    assert invalid.slot_errors.get("gpa") == "must be a number"

    corrected = store.upsert(
        session_id=state.session_id,
        language="en",
        slot_updates={"gpa": 3.5},
    )
    assert "gpa" not in corrected.slot_errors

    snapshot = store.get(state.session_id)
    assert snapshot is not None
    snapshot.slots["target_country"] = "CA"
    # Mutation of snapshot should not change stored state
    persistent = store.get(state.session_id)
    assert persistent.slots["target_country"] == "UK"


def test_session_store_reset_and_prune():
    store = SessionStore(ttl_seconds=60)
    state = store.upsert(
        session_id=None,
        language="en",
        slot_updates={"target_country": "UK", "ielts": "6.0"},
    )

    after_reset = store.upsert(
        session_id=state.session_id,
        language="en",
        slot_updates=None,
        reset_slots=["ielts"],
    )
    assert "ielts" not in after_reset.slots
    assert after_reset.slots["target_country"] == "UK"

    # Force prune by simulating time progression
    store._prune_locked(now=after_reset.updated_at + timedelta(seconds=61))
    assert store.get(state.session_id) is None



def test_session_store_export_and_list():
    store = SessionStore(ttl_seconds=3600)
    state = store.upsert(session_id=None, language="en", slot_updates={"target_country": "US", "ielts": "abc"})

    exported = store.export(state.session_id)
    assert exported is not None
    assert exported.session_id == state.session_id
    assert exported.slots["target_country"] == "US"
    assert exported.slot_errors.get("ielts") == "must be a number"
    assert exported.slot_count == 2
    assert exported.remaining_ttl_seconds is not None
    assert exported.remaining_ttl_seconds <= 3600

    sessions = store.list_sessions()
    assert any(item.session_id == state.session_id for item in sessions)
    for item in sessions:
        if item.session_id == state.session_id:
            assert item.slot_count == 2
            assert item.remaining_ttl_seconds is not None
            break
