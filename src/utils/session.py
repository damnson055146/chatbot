from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional

from src.schemas.models import SessionStateResponse
from src.schemas.slots import filter_valid_slots, normalize_slot_name, slot_definitions, validate_slots


@dataclass
class SessionState:
    session_id: str
    slots: Dict[str, Any] = field(default_factory=dict)
    slot_errors: Dict[str, str] = field(default_factory=dict)
    language: str = "auto"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def copy(self) -> "SessionState":
        return SessionState(
            session_id=self.session_id,
            slots=dict(self.slots),
            slot_errors=dict(self.slot_errors),
            language=self.language,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


def _to_response(state: SessionState, ttl_seconds: int) -> SessionStateResponse:
    now = datetime.now(UTC)
    remaining = int(max((state.updated_at + timedelta(seconds=ttl_seconds) - now).total_seconds(), 0))
    return SessionStateResponse(
        session_id=state.session_id,
        slots=dict(state.slots),
        slot_errors=dict(state.slot_errors),
        language=state.language,
        created_at=state.created_at,
        updated_at=state.updated_at,
        remaining_ttl_seconds=remaining,
        slot_count=len(state.slots),
    )


class SessionStore:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, SessionState] = {}
        self._lock = Lock()

    def _prune_locked(self, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(UTC)
        expiry = now - timedelta(seconds=self.ttl_seconds)
        expired = [sid for sid, state in self._sessions.items() if state.updated_at < expiry]
        for sid in expired:
            self._sessions.pop(sid, None)

    def get(self, session_id: str) -> SessionState | None:
        with self._lock:
            state = self._sessions.get(session_id)
            return state.copy() if state else None

    def upsert(
        self,
        *,
        session_id: str | None,
        language: str,
        slot_updates: Dict[str, Any] | None = None,
        reset_slots: Iterable[str] | None = None,
    ) -> SessionState:
        updates = filter_valid_slots(slot_updates or {})
        validation_errors = validate_slots(updates)
        resets = [normalize_slot_name(k) for k in (reset_slots or [])]
        now = datetime.now(UTC)
        with self._lock:
            self._prune_locked(now)
            state = self._sessions.get(session_id) if session_id else None
            if not state:
                session_id = session_id or uuid.uuid4().hex
                state = SessionState(session_id=session_id)
                self._sessions[session_id] = state
            if language and language != "auto":
                state.language = language
            for key in resets:
                state.slots.pop(key, None)
                state.slot_errors.pop(key, None)
            for key, value in updates.items():
                state.slots[key] = value
                if key in validation_errors:
                    state.slot_errors[key] = validation_errors[key]
                elif key in state.slot_errors:
                    state.slot_errors.pop(key, None)
            # Add errors for required slots if no value provided
            for name, error in validation_errors.items():
                if name not in updates:
                    state.slot_errors[name] = error
            state.updated_at = now
            return state.copy()

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear_all(self) -> None:
        with self._lock:
            self._sessions.clear()

    def export(self, session_id: str) -> SessionStateResponse | None:
        state = self.get(session_id)
        return _to_response(state, self.ttl_seconds) if state else None

    def list_sessions(self) -> List[SessionStateResponse]:
        with self._lock:
            self._prune_locked()
            return [_to_response(state, self.ttl_seconds) for state in self._sessions.values()]

    def snapshot(self) -> Dict[str, SessionState]:
        with self._lock:
            return {sid: state.copy() for sid, state in self._sessions.items()}


_SESSION_STORE: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _SESSION_STORE
    if _SESSION_STORE is None:
        ttl = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
        _SESSION_STORE = SessionStore(ttl_seconds=max(ttl, 60))
    return _SESSION_STORE


def reset_session_store() -> None:
    global _SESSION_STORE
    if _SESSION_STORE is None:
        return
    ttl = _SESSION_STORE.ttl_seconds
    _SESSION_STORE = SessionStore(ttl_seconds=ttl)
