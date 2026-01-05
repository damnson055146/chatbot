from __future__ import annotations

import hashlib
import json
import re
import uuid
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List

from src.schemas.models import SessionStateResponse, UserProfileResponse
from src.schemas.slots import filter_valid_slots, normalize_slot_name, validate_slots
from src.utils import storage
from src.utils.upload_signing import sign_upload_url

_STORE_LOCK = RLock()


def _read_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name, str(default)) or str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


DEFAULT_UPLOAD_RETENTION_DAYS = _read_int_env("UPLOAD_RETENTION_DAYS", 30)


def _sanitize_user_id(user_id: str) -> str:
    raw = user_id.strip() or "anonymous"
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", raw)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{safe[:40]}_{digest}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _conversations_dir() -> Path:
    return storage.DATA_PROCESSED / "conversations"


def _conversation_db_path() -> Path:
    return storage.DATA_PROCESSED / "conversations.sqlite"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _connect_conversation_db() -> sqlite3.Connection:
    storage.ensure_dirs()
    conn = sqlite3.connect(_conversation_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_conversation_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_profiles (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            contact_email TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            pinned INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            language TEXT NOT NULL,
            slots_json TEXT NOT NULL,
            slot_errors_json TEXT NOT NULL,
            summary TEXT,
            summary_updated_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_sessions_user_id ON conversation_sessions(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_sessions_updated_at ON conversation_sessions(updated_at)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_messages_session_id ON conversation_messages(session_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conversation_messages_user_id ON conversation_messages(user_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_messages_session_created ON conversation_messages(session_id, created_at)"
    )
    conn.commit()


def _conversation_is_empty(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) as count FROM conversation_sessions").fetchone()
    if row is None:
        return True
    return int(row["count"] or 0) == 0


_CONVERSATION_DB_READY = False
_CONVERSATION_DB_READY_PATH: Path | None = None


def _initialize_conversation_store() -> None:
    global _CONVERSATION_DB_READY, _CONVERSATION_DB_READY_PATH
    path = _conversation_db_path()
    if _CONVERSATION_DB_READY and _CONVERSATION_DB_READY_PATH == path:
        return
    with _connect_conversation_db() as conn:
        _ensure_conversation_schema(conn)
        if _conversation_is_empty(conn):
            _migrate_file_conversations(conn)
    _CONVERSATION_DB_READY = True
    _CONVERSATION_DB_READY_PATH = path


def _session_row_to_record(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "session_id": row["session_id"],
        "title": row["title"],
        "pinned": bool(row["pinned"]),
        "archived": bool(row["archived"]),
        "language": row["language"] or "auto",
        "slots": _json_loads(row["slots_json"], {}),
        "slot_errors": _json_loads(row["slot_errors_json"], {}),
        "summary": row["summary"] or "",
        "summary_updated_at": row["summary_updated_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _load_message_payload(raw: str) -> Dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(UTC)
    return datetime.now(UTC)


def _derive_title(question: str, max_len: int = 60) -> str:
    trimmed = question.strip()
    if not trimmed:
        return ""
    if len(trimmed) <= max_len:
        return trimmed
    return f"{trimmed[: max_len - 3]}..."


def _user_dir(user_id: str) -> Path:
    storage.ensure_dirs()
    path = _conversations_dir() / _sanitize_user_id(user_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "messages").mkdir(parents=True, exist_ok=True)
    identity_path = path / "identity.json"
    if not identity_path.exists():
        _write_json_dict(identity_path, {"user_id": user_id, "created_at": _now_iso()})
    return path


def _sessions_path(user_id: str) -> Path:
    return _user_dir(user_id) / "sessions.json"


def _messages_path(user_id: str, session_id: str) -> Path:
    return _user_dir(user_id) / "messages" / f"{session_id}.json"


def _profile_path(user_id: str) -> Path:
    return _user_dir(user_id) / "profile.json"


def _sessions_path_from_dir(user_dir: Path) -> Path:
    return user_dir / "sessions.json"


def _messages_path_from_dir(user_dir: Path, session_id: str) -> Path:
    return user_dir / "messages" / f"{session_id}.json"


def _identity_path_from_dir(user_dir: Path) -> Path:
    return user_dir / "identity.json"


def _existing_user_dir(user_id: str) -> Path | None:
    conversations_dir = _conversations_dir()
    direct = conversations_dir / user_id
    if direct.exists():
        return direct
    path = conversations_dir / _sanitize_user_id(user_id)
    if not path.exists():
        return None
    return path


def _load_json_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _write_json_list(path: Path, payload: List[Dict[str, Any]]) -> None:
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _load_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_json_dict(path: Path, payload: Dict[str, Any]) -> None:
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _migrate_file_conversations(conn: sqlite3.Connection) -> None:
    conversations_dir = _conversations_dir()
    if not conversations_dir.exists():
        return
    for user_dir in conversations_dir.iterdir():
        if not user_dir.is_dir():
            continue
        identity = _load_json_dict(_identity_path_from_dir(user_dir))
        user_id = str(identity.get("user_id") or user_dir.name)
        profile_record = _normalize_profile_record(_load_json_dict(user_dir / "profile.json"))
        conn.execute(
            """
            INSERT OR REPLACE INTO conversation_profiles (
                user_id,
                display_name,
                contact_email,
                updated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                profile_record.get("display_name"),
                profile_record.get("contact_email"),
                profile_record.get("updated_at") or _now_iso(),
            ),
        )
        sessions = _load_json_list(_sessions_path_from_dir(user_dir))
        seen_sessions: set[str] = set()
        for record in sessions:
            normalized = _normalize_session_record(record)
            session_id = str(normalized.get("session_id") or uuid.uuid4().hex)
            seen_sessions.add(session_id)
            conn.execute(
                """
                INSERT OR REPLACE INTO conversation_sessions (
                    session_id,
                    user_id,
                    title,
                    pinned,
                    archived,
                    language,
                    slots_json,
                    slot_errors_json,
                    summary,
                    summary_updated_at,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    normalized.get("title"),
                    1 if normalized.get("pinned") else 0,
                    1 if normalized.get("archived") else 0,
                    normalized.get("language") or "auto",
                    _json_dumps(normalized.get("slots") or {}),
                    _json_dumps(normalized.get("slot_errors") or {}),
                    normalized.get("summary") or "",
                    normalized.get("summary_updated_at"),
                    str(normalized.get("created_at") or _now_iso()),
                    str(normalized.get("updated_at") or _now_iso()),
                ),
            )
        messages_dir = user_dir / "messages"
        if messages_dir.exists():
            for path in messages_dir.glob("*.json"):
                session_id = path.stem
                if session_id not in seen_sessions:
                    fallback_record = _normalize_session_record(
                        {"session_id": session_id, "language": "auto"}
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO conversation_sessions (
                            session_id,
                            user_id,
                            title,
                            pinned,
                            archived,
                            language,
                            slots_json,
                            slot_errors_json,
                            summary,
                            summary_updated_at,
                            created_at,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session_id,
                            user_id,
                            fallback_record.get("title"),
                            1 if fallback_record.get("pinned") else 0,
                            1 if fallback_record.get("archived") else 0,
                            fallback_record.get("language") or "auto",
                            _json_dumps(fallback_record.get("slots") or {}),
                            _json_dumps(fallback_record.get("slot_errors") or {}),
                            fallback_record.get("summary") or "",
                            fallback_record.get("summary_updated_at"),
                            str(fallback_record.get("created_at") or _now_iso()),
                            str(fallback_record.get("updated_at") or _now_iso()),
                        ),
                    )
                    seen_sessions.add(session_id)
                messages = _load_json_list(path)
                for message in messages:
                    if not isinstance(message, dict):
                        continue
                    message_id = str(message.get("id") or uuid.uuid4().hex)
                    message["id"] = message_id
                    created_at = str(message.get("created_at") or _now_iso())
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO conversation_messages (
                            id,
                            session_id,
                            user_id,
                            created_at,
                            payload_json
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            message_id,
                            session_id,
                            user_id,
                            created_at,
                            _json_dumps(message),
                        ),
                    )
    conn.commit()


def _normalize_session_record(record: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    normalized = dict(record)
    normalized.setdefault("session_id", uuid.uuid4().hex)
    normalized.setdefault("title", None)
    normalized.setdefault("pinned", False)
    normalized.setdefault("archived", False)
    normalized.setdefault("language", "auto")
    normalized.setdefault("slots", {})
    normalized.setdefault("slot_errors", {})
    normalized.setdefault("summary", "")
    normalized.setdefault("summary_updated_at", None)
    normalized.setdefault("created_at", now)
    normalized.setdefault("updated_at", now)
    if not isinstance(normalized.get("slots"), dict):
        normalized["slots"] = {}
    if not isinstance(normalized.get("slot_errors"), dict):
        normalized["slot_errors"] = {}
    return normalized


def _session_to_response(record: Dict[str, Any]) -> SessionStateResponse:
    slots = record.get("slots") if isinstance(record.get("slots"), dict) else {}
    slot_errors = record.get("slot_errors") if isinstance(record.get("slot_errors"), dict) else {}
    return SessionStateResponse(
        session_id=str(record.get("session_id")),
        slots=slots,
        slot_errors=slot_errors,
        language=str(record.get("language") or "auto"),
        created_at=_parse_datetime(record.get("created_at")),
        updated_at=_parse_datetime(record.get("updated_at")),
        remaining_ttl_seconds=None,
        slot_count=len(slots),
        title=record.get("title"),
        pinned=bool(record.get("pinned", False)),
        archived=bool(record.get("archived", False)),
    )


def _normalize_profile_record(record: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    normalized = dict(record)
    normalized.setdefault("display_name", None)
    normalized.setdefault("contact_email", None)
    normalized.setdefault("updated_at", now)
    return normalized


def _profile_to_response(record: Dict[str, Any]) -> UserProfileResponse:
    return UserProfileResponse(
        display_name=record.get("display_name"),
        contact_email=record.get("contact_email"),
        updated_at=_parse_datetime(record.get("updated_at")) if record.get("updated_at") else None,
    )


def _clean_profile_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value).strip() or None


def _attachment_record(upload_id: str) -> Dict[str, Any]:
    record = storage.load_upload_record(upload_id)
    if record is None:
        return {
            "client_id": f"att-{upload_id}",
            "upload_id": upload_id,
            "filename": upload_id,
            "mime_type": "application/octet-stream",
            "size_bytes": 0,
            "status": "error",
            "error": "Upload not found",
        }
    return {
        "client_id": f"att-{record.upload_id}",
        "upload_id": record.upload_id,
        "filename": record.filename,
        "mime_type": record.mime_type,
        "size_bytes": record.size_bytes,
        "status": "ready",
        "error": None,
    }


def _refresh_attachment(record: Dict[str, Any]) -> Dict[str, Any]:
    attachment = dict(record)
    upload_id = attachment.get("upload_id")
    if not isinstance(upload_id, str) or not upload_id:
        return attachment
    if not attachment.get("client_id"):
        attachment["client_id"] = f"att-{upload_id}"
    upload = storage.load_upload_record(upload_id)
    if upload is None:
        attachment["download_url"] = None
        attachment["status"] = "error"
        attachment["error"] = "Upload not found"
        return attachment
    if storage.is_upload_expired(upload, default_retention_days=DEFAULT_UPLOAD_RETENTION_DAYS):
        attachment["download_url"] = None
        attachment["status"] = "error"
        attachment["error"] = "Upload expired"
        return attachment
    attachment.setdefault("filename", upload.filename)
    attachment.setdefault("mime_type", upload.mime_type)
    attachment.setdefault("size_bytes", upload.size_bytes)
    signed = sign_upload_url(upload_id, base_path=f"/v1/upload/{upload_id}/file", disposition="attachment")
    attachment["download_url"] = signed.url
    return attachment


class FileConversationStore:
    """Legacy file-backed conversation store grouped by user id."""

    def list_users(self, limit: int | None = None) -> List[Dict[str, Any]]:
        conversations_dir = _conversations_dir()
        if not conversations_dir.exists():
            return []
        entries: List[Dict[str, Any]] = []
        with _STORE_LOCK:
            for user_dir in conversations_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                identity = _load_json_dict(_identity_path_from_dir(user_dir))
                profile = _normalize_profile_record(_load_json_dict(user_dir / "profile.json"))
                sessions = _load_json_list(_sessions_path_from_dir(user_dir))
                last_active = None
                for record in sessions:
                    updated = _parse_datetime(record.get("updated_at"))
                    if last_active is None or updated > last_active:
                        last_active = updated
                entries.append(
                    {
                        "user_id": identity.get("user_id") or user_dir.name,
                        "display_name": profile.get("display_name"),
                        "contact_email": profile.get("contact_email"),
                        "session_count": len(sessions),
                        "last_active_at": last_active,
                    }
                )
        entries.sort(key=lambda item: item.get("last_active_at") or datetime.min.replace(tzinfo=UTC), reverse=True)
        if limit is not None and limit > 0:
            return entries[:limit]
        return entries

    def list_sessions_admin(self, *, user_id: str | None = None, limit: int | None = None) -> List[Dict[str, Any]]:
        sessions: List[Dict[str, Any]] = []
        with _STORE_LOCK:
            if user_id:
                user_dir = _existing_user_dir(user_id)
                if user_dir is None:
                    return []
                records = _load_json_list(_sessions_path_from_dir(user_dir))
                identity = _load_json_dict(_identity_path_from_dir(user_dir))
                user_value = identity.get("user_id") or user_id
                for record in records:
                    response = _session_to_response(_normalize_session_record(record))
                    sessions.append(
                        {
                            "user_id": user_value,
                            "session_id": response.session_id,
                            "title": response.title,
                            "language": response.language,
                            "slot_count": response.slot_count,
                            "pinned": response.pinned,
                            "archived": response.archived,
                            "created_at": response.created_at,
                            "updated_at": response.updated_at,
                        }
                    )
            else:
                conversations_dir = _conversations_dir()
                if conversations_dir.exists():
                    for user_dir in conversations_dir.iterdir():
                        if not user_dir.is_dir():
                            continue
                        identity = _load_json_dict(_identity_path_from_dir(user_dir))
                        user_value = identity.get("user_id") or user_dir.name
                        records = _load_json_list(_sessions_path_from_dir(user_dir))
                        for record in records:
                            response = _session_to_response(_normalize_session_record(record))
                            sessions.append(
                                {
                                    "user_id": user_value,
                                    "session_id": response.session_id,
                                    "title": response.title,
                                    "language": response.language,
                                    "slot_count": response.slot_count,
                                    "pinned": response.pinned,
                                    "archived": response.archived,
                                    "created_at": response.created_at,
                                    "updated_at": response.updated_at,
                                }
                            )
        sessions.sort(key=lambda item: item["updated_at"], reverse=True)
        if limit is not None and limit > 0:
            return sessions[:limit]
        return sessions

    def list_messages_admin(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        user_dir = _existing_user_dir(user_id)
        if user_dir is None:
            return []
        with _STORE_LOCK:
            messages = _load_json_list(_messages_path_from_dir(user_dir, session_id))
        hydrated = []
        for message in messages:
            normalized = dict(message)
            attachments = normalized.get("attachments", [])
            if isinstance(attachments, list):
                normalized["attachments"] = [_refresh_attachment(item) for item in attachments if isinstance(item, dict)]
            hydrated.append(normalized)
        return hydrated

    def get_profile(self, user_id: str) -> UserProfileResponse:
        with _STORE_LOCK:
            record = _load_json_dict(_profile_path(user_id))
        record = _normalize_profile_record(record)
        return _profile_to_response(record)

    def update_profile(self, user_id: str, updates: Dict[str, Any]) -> UserProfileResponse:
        now = _now_iso()
        with _STORE_LOCK:
            profile_path = _profile_path(user_id)
            record = _load_json_dict(profile_path)
            record = _normalize_profile_record(record)
            if "display_name" in updates:
                record["display_name"] = _clean_profile_value(updates.get("display_name"))
            if "contact_email" in updates:
                record["contact_email"] = _clean_profile_value(updates.get("contact_email"))
            record["updated_at"] = now
            _write_json_dict(profile_path, record)
        return _profile_to_response(record)

    def list_sessions(self, user_id: str) -> List[SessionStateResponse]:
        with _STORE_LOCK:
            records = _load_json_list(_sessions_path(user_id))
        records = [_normalize_session_record(record) for record in records]
        records.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return [_session_to_response(record) for record in records]

    def count_sessions(self) -> int:
        conversations_dir = _conversations_dir()
        if not conversations_dir.exists():
            return 0
        total = 0
        for entry in conversations_dir.iterdir():
            if not entry.is_dir():
                continue
            sessions_path = entry / "sessions.json"
            total += len(_load_json_list(sessions_path))
        return total

    def get_session(self, user_id: str, session_id: str) -> SessionStateResponse | None:
        with _STORE_LOCK:
            records = _load_json_list(_sessions_path(user_id))
        for record in records:
            if record.get("session_id") == session_id:
                return _session_to_response(_normalize_session_record(record))
        return None

    def get_session_summary(self, user_id: str, session_id: str) -> str:
        with _STORE_LOCK:
            records = _load_json_list(_sessions_path(user_id))
        for record in records:
            if record.get("session_id") == session_id:
                summary = record.get("summary")
                if isinstance(summary, str):
                    return summary.strip()
                return ""
        return ""

    def create_session(
        self,
        user_id: str,
        *,
        title: str | None = None,
        language: str | None = None,
        session_id: str | None = None,
    ) -> SessionStateResponse:
        record = _normalize_session_record(
            {
                "session_id": session_id or uuid.uuid4().hex,
                "title": title,
                "language": language or "auto",
            }
        )
        with _STORE_LOCK:
            sessions_path = _sessions_path(user_id)
            records = _load_json_list(sessions_path)
            records.append(record)
            _write_json_list(sessions_path, records)
        return _session_to_response(record)

    def upsert_session(
        self,
        user_id: str,
        *,
        session_id: str | None,
        language: str,
        slot_updates: Dict[str, Any] | None,
        reset_slots: Iterable[str] | None,
    ) -> SessionStateResponse:
        updates = filter_valid_slots(slot_updates or {})
        validation_errors = validate_slots(updates)
        resets = [normalize_slot_name(name) for name in (reset_slots or [])]
        now = _now_iso()
        with _STORE_LOCK:
            sessions_path = _sessions_path(user_id)
            records = _load_json_list(sessions_path)
            record = None
            record_index = None
            for idx, item in enumerate(records):
                if session_id and item.get("session_id") == session_id:
                    record = item
                    record_index = idx
                    break
            if record is None:
                record = _normalize_session_record(
                    {
                        "session_id": session_id or uuid.uuid4().hex,
                        "language": language,
                    }
                )
                records.append(record)
                record_index = len(records) - 1
            record = _normalize_session_record(record)
            if language and language != "auto":
                record["language"] = language
            slots = record.get("slots", {})
            slot_errors = record.get("slot_errors", {})
            for key in resets:
                slots.pop(key, None)
                slot_errors.pop(key, None)
            for key, value in updates.items():
                slots[key] = value
                if key in validation_errors:
                    slot_errors[key] = validation_errors[key]
                elif key in slot_errors:
                    slot_errors.pop(key, None)
            record["slots"] = slots
            record["slot_errors"] = slot_errors
            record["updated_at"] = now
            if record_index is not None:
                records[record_index] = record
            _write_json_list(sessions_path, records)
        return _session_to_response(record)

    def update_session_metadata(
        self,
        user_id: str,
        session_id: str,
        *,
        title: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> SessionStateResponse | None:
        now = _now_iso()
        with _STORE_LOCK:
            sessions_path = _sessions_path(user_id)
            records = _load_json_list(sessions_path)
            record = None
            record_index = None
            for idx, item in enumerate(records):
                if item.get("session_id") == session_id:
                    record = item
                    record_index = idx
                    break
            if record is None:
                return None
            record = _normalize_session_record(record)
            if title is not None:
                record["title"] = title
            if pinned is not None:
                record["pinned"] = bool(pinned)
            if archived is not None:
                record["archived"] = bool(archived)
            record["updated_at"] = now
            if record_index is not None:
                records[record_index] = record
            _write_json_list(sessions_path, records)
        return _session_to_response(record)

    def update_session_summary(self, user_id: str, session_id: str, summary: str) -> bool:
        cleaned = summary.strip()
        now = _now_iso()
        with _STORE_LOCK:
            sessions_path = _sessions_path(user_id)
            records = _load_json_list(sessions_path)
            for idx, record in enumerate(records):
                if record.get("session_id") != session_id:
                    continue
                normalized = _normalize_session_record(record)
                normalized["summary"] = cleaned
                normalized["summary_updated_at"] = now
                records[idx] = normalized
                _write_json_list(sessions_path, records)
                return True
        return False

    def delete_session(self, user_id: str, session_id: str) -> bool:
        removed = False
        with _STORE_LOCK:
            sessions_path = _sessions_path(user_id)
            records = _load_json_list(sessions_path)
            filtered = [item for item in records if item.get("session_id") != session_id]
            if len(filtered) != len(records):
                _write_json_list(sessions_path, filtered)
                removed = True
        messages_path = _messages_path(user_id, session_id)
        if messages_path.exists():
            messages_path.unlink(missing_ok=True)
            removed = True
        return removed

    def list_messages(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        with _STORE_LOCK:
            messages = _load_json_list(_messages_path(user_id, session_id))
        hydrated = []
        for message in messages:
            normalized = dict(message)
            attachments = normalized.get("attachments", [])
            if isinstance(attachments, list):
                normalized["attachments"] = [_refresh_attachment(item) for item in attachments if isinstance(item, dict)]
            hydrated.append(normalized)
        return hydrated

    def append_message(self, user_id: str, session_id: str, message: Dict[str, Any]) -> None:
        now = _now_iso()
        message.setdefault("created_at", now)
        with _STORE_LOCK:
            sessions_path = _sessions_path(user_id)
            records = _load_json_list(sessions_path)
            record = None
            record_index = None
            for idx, item in enumerate(records):
                if item.get("session_id") == session_id:
                    record = item
                    record_index = idx
                    break
            if record is None:
                record = _normalize_session_record({"session_id": session_id})
                records.append(record)
                record_index = len(records) - 1
            record = _normalize_session_record(record)
            record["updated_at"] = now
            if message.get("role") == "user" and not record.get("title"):
                record["title"] = _derive_title(str(message.get("content") or ""))
            if record_index is not None:
                records[record_index] = record
            _write_json_list(sessions_path, records)

            messages_path = _messages_path(user_id, session_id)
            messages = _load_json_list(messages_path)
            messages.append(message)
            _write_json_list(messages_path, messages)

    def build_attachment_records(self, upload_ids: Iterable[str]) -> List[Dict[str, Any]]:
        attachments: List[Dict[str, Any]] = []
        for upload_id in upload_ids:
            if not upload_id:
                continue
            attachments.append(_attachment_record(upload_id))
        return attachments


class ConversationStore:
    """SQLite-backed conversation store grouped by user id."""

    def __init__(self) -> None:
        _initialize_conversation_store()

    def _connect(self) -> sqlite3.Connection:
        _initialize_conversation_store()
        return _connect_conversation_db()

    def list_users(self, limit: int | None = None) -> List[Dict[str, Any]]:
        query = (
            "SELECT s.user_id as user_id, COUNT(*) as session_count, "
            "MAX(s.updated_at) as last_active, p.display_name as display_name, "
            "p.contact_email as contact_email "
            "FROM conversation_sessions s "
            "LEFT JOIN conversation_profiles p ON p.user_id = s.user_id "
            "GROUP BY s.user_id "
            "ORDER BY last_active DESC"
        )
        params: tuple[Any, ...] = ()
        if limit is not None and limit > 0:
            query = f"{query} LIMIT ?"
            params = (limit,)
        with _STORE_LOCK, self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        entries: List[Dict[str, Any]] = []
        for row in rows:
            last_active_value = row["last_active"]
            entries.append(
                {
                    "user_id": row["user_id"],
                    "display_name": row["display_name"],
                    "contact_email": row["contact_email"],
                    "session_count": int(row["session_count"] or 0),
                    "last_active_at": _parse_datetime(last_active_value) if last_active_value else None,
                }
            )
        return entries

    def list_sessions_admin(self, *, user_id: str | None = None, limit: int | None = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM conversation_sessions"
        params: List[Any] = []
        if user_id:
            query = f"{query} WHERE user_id = ?"
            params.append(user_id)
        query = f"{query} ORDER BY updated_at DESC"
        if limit is not None and limit > 0:
            query = f"{query} LIMIT ?"
            params.append(limit)
        with _STORE_LOCK, self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        sessions: List[Dict[str, Any]] = []
        for row in rows:
            record = _normalize_session_record(_session_row_to_record(row))
            response = _session_to_response(record)
            sessions.append(
                {
                    "user_id": row["user_id"],
                    "session_id": response.session_id,
                    "title": response.title,
                    "language": response.language,
                    "slot_count": response.slot_count,
                    "pinned": response.pinned,
                    "archived": response.archived,
                    "created_at": response.created_at,
                    "updated_at": response.updated_at,
                }
            )
        return sessions

    def list_messages_admin(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        with _STORE_LOCK, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM conversation_messages
                WHERE user_id = ? AND session_id = ?
                ORDER BY created_at ASC
                """,
                (user_id, session_id),
            ).fetchall()
        hydrated = []
        for row in rows:
            payload = _load_message_payload(row["payload_json"])
            if not payload:
                continue
            attachments = payload.get("attachments", [])
            if isinstance(attachments, list):
                payload["attachments"] = [_refresh_attachment(item) for item in attachments if isinstance(item, dict)]
            hydrated.append(payload)
        return hydrated

    def get_profile(self, user_id: str) -> UserProfileResponse:
        with _STORE_LOCK, self._connect() as conn:
            row = conn.execute(
                """
                SELECT display_name, contact_email, updated_at
                FROM conversation_profiles
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        record: Dict[str, Any] = dict(row) if row else {}
        record = _normalize_profile_record(record)
        return _profile_to_response(record)

    def update_profile(self, user_id: str, updates: Dict[str, Any]) -> UserProfileResponse:
        now = _now_iso()
        with _STORE_LOCK, self._connect() as conn:
            row = conn.execute(
                """
                SELECT display_name, contact_email, updated_at
                FROM conversation_profiles
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
            record = _normalize_profile_record(dict(row) if row else {})
            if "display_name" in updates:
                record["display_name"] = _clean_profile_value(updates.get("display_name"))
            if "contact_email" in updates:
                record["contact_email"] = _clean_profile_value(updates.get("contact_email"))
            record["updated_at"] = now
            conn.execute(
                """
                INSERT OR REPLACE INTO conversation_profiles (
                    user_id,
                    display_name,
                    contact_email,
                    updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    record.get("display_name"),
                    record.get("contact_email"),
                    record.get("updated_at"),
                ),
            )
        return _profile_to_response(record)

    def list_sessions(self, user_id: str) -> List[SessionStateResponse]:
        with _STORE_LOCK, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM conversation_sessions
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        records = [_normalize_session_record(_session_row_to_record(row)) for row in rows]
        return [_session_to_response(record) for record in records]

    def count_sessions(self) -> int:
        with _STORE_LOCK, self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM conversation_sessions").fetchone()
        if row is None:
            return 0
        return int(row["count"] or 0)

    def get_session(self, user_id: str, session_id: str) -> SessionStateResponse | None:
        with _STORE_LOCK, self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM conversation_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()
        if row is None:
            return None
        record = _normalize_session_record(_session_row_to_record(row))
        return _session_to_response(record)

    def get_session_summary(self, user_id: str, session_id: str) -> str:
        with _STORE_LOCK, self._connect() as conn:
            row = conn.execute(
                """
                SELECT summary
                FROM conversation_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()
        if row is None:
            return ""
        summary = row["summary"]
        if isinstance(summary, str):
            return summary.strip()
        return ""

    def create_session(
        self,
        user_id: str,
        *,
        title: str | None = None,
        language: str | None = None,
        session_id: str | None = None,
    ) -> SessionStateResponse:
        record = _normalize_session_record(
            {
                "session_id": session_id or uuid.uuid4().hex,
                "title": title,
                "language": language or "auto",
            }
        )
        with _STORE_LOCK, self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO conversation_sessions (
                    session_id,
                    user_id,
                    title,
                    pinned,
                    archived,
                    language,
                    slots_json,
                    slot_errors_json,
                    summary,
                    summary_updated_at,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("session_id"),
                    user_id,
                    record.get("title"),
                    1 if record.get("pinned") else 0,
                    1 if record.get("archived") else 0,
                    record.get("language") or "auto",
                    _json_dumps(record.get("slots") or {}),
                    _json_dumps(record.get("slot_errors") or {}),
                    record.get("summary") or "",
                    record.get("summary_updated_at"),
                    str(record.get("created_at") or _now_iso()),
                    str(record.get("updated_at") or _now_iso()),
                ),
            )
            row = conn.execute(
                """
                SELECT *
                FROM conversation_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, record.get("session_id")),
            ).fetchone()
        if row is not None:
            record = _normalize_session_record(_session_row_to_record(row))
        return _session_to_response(record)

    def upsert_session(
        self,
        user_id: str,
        *,
        session_id: str | None,
        language: str,
        slot_updates: Dict[str, Any] | None,
        reset_slots: Iterable[str] | None,
    ) -> SessionStateResponse:
        updates = filter_valid_slots(slot_updates or {})
        validation_errors = validate_slots(updates)
        resets = [normalize_slot_name(name) for name in (reset_slots or [])]
        now = _now_iso()
        session_id_value = session_id or uuid.uuid4().hex
        with _STORE_LOCK, self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM conversation_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id_value),
            ).fetchone()
            if row is None:
                record = _normalize_session_record(
                    {
                        "session_id": session_id_value,
                        "language": language,
                    }
                )
            else:
                record = _normalize_session_record(_session_row_to_record(row))
            if language and language != "auto":
                record["language"] = language
            slots = record.get("slots", {})
            slot_errors = record.get("slot_errors", {})
            for key in resets:
                slots.pop(key, None)
                slot_errors.pop(key, None)
            for key, value in updates.items():
                slots[key] = value
                if key in validation_errors:
                    slot_errors[key] = validation_errors[key]
                elif key in slot_errors:
                    slot_errors.pop(key, None)
            record["slots"] = slots
            record["slot_errors"] = slot_errors
            record["updated_at"] = now
            if row is None:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO conversation_sessions (
                        session_id,
                        user_id,
                        title,
                        pinned,
                        archived,
                        language,
                        slots_json,
                        slot_errors_json,
                        summary,
                        summary_updated_at,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.get("session_id"),
                        user_id,
                        record.get("title"),
                        1 if record.get("pinned") else 0,
                        1 if record.get("archived") else 0,
                        record.get("language") or "auto",
                        _json_dumps(record.get("slots") or {}),
                        _json_dumps(record.get("slot_errors") or {}),
                        record.get("summary") or "",
                        record.get("summary_updated_at"),
                        str(record.get("created_at") or _now_iso()),
                        str(record.get("updated_at") or _now_iso()),
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE conversation_sessions
                    SET title = ?, pinned = ?, archived = ?, language = ?, slots_json = ?, slot_errors_json = ?,
                        summary = ?, summary_updated_at = ?, updated_at = ?
                    WHERE user_id = ? AND session_id = ?
                    """,
                    (
                        record.get("title"),
                        1 if record.get("pinned") else 0,
                        1 if record.get("archived") else 0,
                        record.get("language") or "auto",
                        _json_dumps(record.get("slots") or {}),
                        _json_dumps(record.get("slot_errors") or {}),
                        record.get("summary") or "",
                        record.get("summary_updated_at"),
                        record.get("updated_at") or _now_iso(),
                        user_id,
                        record.get("session_id"),
                    ),
                )
        return _session_to_response(record)

    def update_session_metadata(
        self,
        user_id: str,
        session_id: str,
        *,
        title: str | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> SessionStateResponse | None:
        now = _now_iso()
        with _STORE_LOCK, self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM conversation_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()
            if row is None:
                return None
            record = _normalize_session_record(_session_row_to_record(row))
            if title is not None:
                record["title"] = title
            if pinned is not None:
                record["pinned"] = bool(pinned)
            if archived is not None:
                record["archived"] = bool(archived)
            record["updated_at"] = now
            conn.execute(
                """
                UPDATE conversation_sessions
                SET title = ?, pinned = ?, archived = ?, updated_at = ?
                WHERE user_id = ? AND session_id = ?
                """,
                (
                    record.get("title"),
                    1 if record.get("pinned") else 0,
                    1 if record.get("archived") else 0,
                    record.get("updated_at") or _now_iso(),
                    user_id,
                    record.get("session_id"),
                ),
            )
        return _session_to_response(record)

    def update_session_summary(self, user_id: str, session_id: str, summary: str) -> bool:
        cleaned = summary.strip()
        now = _now_iso()
        with _STORE_LOCK, self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE conversation_sessions
                SET summary = ?, summary_updated_at = ?, updated_at = ?
                WHERE user_id = ? AND session_id = ?
                """,
                (cleaned, now, now, user_id, session_id),
            )
        return cursor.rowcount > 0

    def delete_session(self, user_id: str, session_id: str) -> bool:
        with _STORE_LOCK, self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM conversation_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            )
        return cursor.rowcount > 0

    def list_messages(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        with _STORE_LOCK, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM conversation_messages
                WHERE user_id = ? AND session_id = ?
                ORDER BY created_at ASC
                """,
                (user_id, session_id),
            ).fetchall()
        hydrated = []
        for row in rows:
            payload = _load_message_payload(row["payload_json"])
            if not payload:
                continue
            attachments = payload.get("attachments", [])
            if isinstance(attachments, list):
                payload["attachments"] = [_refresh_attachment(item) for item in attachments if isinstance(item, dict)]
            hydrated.append(payload)
        return hydrated

    def append_message(self, user_id: str, session_id: str, message: Dict[str, Any]) -> None:
        now = _now_iso()
        message.setdefault("created_at", now)
        message_id = str(message.get("id") or uuid.uuid4().hex)
        message["id"] = message_id
        with _STORE_LOCK, self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM conversation_sessions
                WHERE user_id = ? AND session_id = ?
                """,
                (user_id, session_id),
            ).fetchone()
            if row is None:
                record = _normalize_session_record({"session_id": session_id})
                if message.get("role") == "user" and not record.get("title"):
                    record["title"] = _derive_title(str(message.get("content") or ""))
                record["updated_at"] = now
                conn.execute(
                    """
                    INSERT OR REPLACE INTO conversation_sessions (
                        session_id,
                        user_id,
                        title,
                        pinned,
                        archived,
                        language,
                        slots_json,
                        slot_errors_json,
                        summary,
                        summary_updated_at,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.get("session_id"),
                        user_id,
                        record.get("title"),
                        1 if record.get("pinned") else 0,
                        1 if record.get("archived") else 0,
                        record.get("language") or "auto",
                        _json_dumps(record.get("slots") or {}),
                        _json_dumps(record.get("slot_errors") or {}),
                        record.get("summary") or "",
                        record.get("summary_updated_at"),
                        str(record.get("created_at") or _now_iso()),
                        str(record.get("updated_at") or _now_iso()),
                    ),
                )
            else:
                record = _normalize_session_record(_session_row_to_record(row))
                record["updated_at"] = now
                if message.get("role") == "user" and not record.get("title"):
                    record["title"] = _derive_title(str(message.get("content") or ""))
                conn.execute(
                    """
                    UPDATE conversation_sessions
                    SET title = ?, updated_at = ?
                    WHERE user_id = ? AND session_id = ?
                    """,
                    (
                        record.get("title"),
                        record.get("updated_at") or _now_iso(),
                        user_id,
                        record.get("session_id"),
                    ),
                )
            conn.execute(
                """
                INSERT OR REPLACE INTO conversation_messages (
                    id,
                    session_id,
                    user_id,
                    created_at,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_id,
                    user_id,
                    str(message.get("created_at") or now),
                    _json_dumps(message),
                ),
            )

    def build_attachment_records(self, upload_ids: Iterable[str]) -> List[Dict[str, Any]]:
        attachments: List[Dict[str, Any]] = []
        for upload_id in upload_ids:
            if not upload_id:
                continue
            attachments.append(_attachment_record(upload_id))
        return attachments


_STORE: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _STORE
    if _STORE is None:
        _STORE = ConversationStore()
    return _STORE
