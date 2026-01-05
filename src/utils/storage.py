from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
import re
from threading import RLock
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.schemas.models import Document, UploadRecord
from src.schemas.slots import SlotDefinition

from .chunking import Chunk

DATA_RAW = Path("assets/data/raw")
DATA_PROCESSED = Path("assets/data/processed")
DATA_SNAPSHOTS = Path("assets/data/snapshots")
UPLOADS_DIR = Path("assets/uploads")
ASSISTANT_AVATAR_PREFIX = "assistant_avatar"
ASSISTANT_AVATAR_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
MANIFEST_PATH = DATA_PROCESSED / "manifest.json"
SLOTS_PATH = DATA_PROCESSED / "slots.json"
RETRIEVAL_SETTINGS_PATH = DATA_PROCESSED / "retrieval.json"
AUDIT_LOG_PATH = DATA_PROCESSED / "audit.log"
STOP_LIST_PATH = DATA_PROCESSED / "stop_list.json"
JOBS_PATH = DATA_PROCESSED / "jobs.json"
TEMPLATES_PATH = DATA_PROCESSED / "templates.json"
PROMPTS_PATH = DATA_PROCESSED / "prompts.json"
ASSISTANT_PROFILE_PATH = DATA_PROCESSED / "assistant_profile.json"
ESCALATIONS_PATH = DATA_PROCESSED / "escalations.json"
METRICS_HISTORY_MAX = 500
STATUS_HISTORY_MAX = 500
METRICS_SNAPSHOT_MIN_INTERVAL_SECONDS = 60
STATUS_SNAPSHOT_MIN_INTERVAL_SECONDS = 60

DEFAULT_ASSISTANT_PROFILE = {
    "name": "Lumi",
    "avatar": {
        "accent": "#2563eb",
        "base": "#e0f2ff",
        "ring": "#bfdbfe",
        "face": "#0f172a",
        "image_url": None,
    },
}


_MANIFEST_CACHE: Optional[List[Document]] = None
_MANIFEST_MTIME: Optional[float] = None
_PROMPTS_CACHE: Optional[List[Dict[str, Any]]] = None
_PROMPTS_MTIME: Optional[float] = None

_JOB_HISTORY_LOCK = RLock()
_ESCALATIONS_LOCK = RLock()
_METRICS_HISTORY_LOCK = RLock()
_STATUS_HISTORY_LOCK = RLock()
_METADATA_READY = False
_METADATA_READY_PATH: Path | None = None


def _metadata_db_path() -> Path:
    return DATA_PROCESSED / "metadata.sqlite"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _metadata_mtime() -> float | None:
    path = _metadata_db_path()
    if not path.exists():
        return None
    return path.stat().st_mtime


def _connect_metadata_db() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(_metadata_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect_metadata_db() -> sqlite3.Connection:
    """Open the metadata database with schema ensured."""

    ensure_dirs()
    _initialize_metadata_store()
    conn = sqlite3.connect(_metadata_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_metadata_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            doc_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            language TEXT,
            url TEXT,
            domain TEXT,
            freshness TEXT,
            checksum TEXT,
            version INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            tags TEXT,
            extra TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            text TEXT NOT NULL,
            start_idx INTEGER,
            end_idx INTEGER,
            metadata TEXT,
            FOREIGN KEY(doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            reset_question TEXT,
            reset_answer_hash TEXT,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "reset_question" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN reset_question TEXT")
    if "reset_answer_hash" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN reset_answer_hash TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            snapshot_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS status_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status_json TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _metadata_is_empty(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) as count FROM documents").fetchone()
    if row is None:
        return True
    return int(row["count"] or 0) == 0


def _load_manifest_json() -> List[Document]:
    if not MANIFEST_PATH.exists():
        return []
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return [Document.model_validate(item) for item in payload]


def _load_chunks_json(doc_id: str) -> List[Chunk]:
    path = DATA_PROCESSED / f"{doc_id}.chunks.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Chunk(**item) for item in payload]


def _migrate_json_to_sqlite(conn: sqlite3.Connection) -> None:
    docs = _load_manifest_json()
    if not docs:
        for path in DATA_PROCESSED.glob("*.chunks.json"):
            doc_id = path.name.replace(".chunks.json", "")
            docs.append(
                Document(
                    doc_id=doc_id,
                    source_name=doc_id,
                    updated_at=datetime.now(UTC),
                )
            )
    if not docs:
        return

    conn.execute("DELETE FROM documents")
    for doc in docs:
        conn.execute(
            """
            INSERT OR REPLACE INTO documents (
                doc_id,
                source_name,
                language,
                url,
                domain,
                freshness,
                checksum,
                version,
                updated_at,
                tags,
                extra
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc.doc_id,
                doc.source_name,
                doc.language,
                doc.url,
                doc.domain,
                doc.freshness,
                doc.checksum,
                doc.version,
                doc.updated_at.isoformat(),
                _json_dumps(doc.tags or []),
                _json_dumps(doc.extra or {}),
            ),
        )
        chunk_rows = _load_chunks_json(doc.doc_id)
        if not chunk_rows:
            continue
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc.doc_id,))
        conn.executemany(
            """
            INSERT OR REPLACE INTO chunks (
                chunk_id,
                doc_id,
                text,
                start_idx,
                end_idx,
                metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    chunk.chunk_id,
                    chunk.doc_id,
                    chunk.text,
                    chunk.start_idx,
                    chunk.end_idx,
                    _json_dumps(chunk.metadata or {}),
                )
                for chunk in chunk_rows
            ],
        )
    conn.commit()


def _initialize_metadata_store() -> None:
    global _METADATA_READY, _METADATA_READY_PATH
    path = _metadata_db_path()
    if _METADATA_READY and _METADATA_READY_PATH == path:
        return
    with _connect_metadata_db() as conn:
        _ensure_metadata_schema(conn)
        if _metadata_is_empty(conn):
            _migrate_json_to_sqlite(conn)
    _METADATA_READY = True
    _METADATA_READY_PATH = path




def _cache_dir() -> Path:
    return DATA_PROCESSED / "cache"


def _doc_lookup_cache_path() -> Path:
    return _cache_dir() / "doc_lookup.json"


def _load_cached_doc_lookup(manifest_mtime: float | None) -> dict[str, Document] | None:
    if manifest_mtime is None:
        return None
    cache_path = _doc_lookup_cache_path()
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        cache_path.unlink(missing_ok=True)
        return None
    cached_mtime = payload.get("manifest_mtime")
    if not isinstance(cached_mtime, (int, float)) or abs(cached_mtime - manifest_mtime) > 1e-6:
        return None
    docs_payload = payload.get("docs")
    if not isinstance(docs_payload, list):
        return None
    try:
        docs = [Document.model_validate(item) for item in docs_payload]
    except Exception:
        cache_path.unlink(missing_ok=True)
        return None
    return {doc.doc_id: doc for doc in docs}


def _write_doc_lookup_cache(manifest_mtime: float, docs: Iterable[Document]) -> None:
    cache_path = _doc_lookup_cache_path()
    cache_dir = cache_path.parent
    cache_dir.mkdir(parents=True, exist_ok=True)
    serialized_docs = []
    for doc in docs:
        serialized_docs.append(doc.model_dump(mode="json"))
    payload = {
        "manifest_mtime": manifest_mtime,
        "docs": serialized_docs,
    }
    tmp_path = cache_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(cache_path)


def get_doc_lookup() -> Dict[str, Document]:
    ensure_dirs()
    _initialize_metadata_store()
    manifest_mtime = _metadata_mtime()
    if manifest_mtime is None:
        return {}
    cached = _load_cached_doc_lookup(manifest_mtime)
    if cached is not None:
        return {key: value.model_copy() for key, value in cached.items()}
    docs = load_manifest()
    doc_lookup = {doc.doc_id: doc for doc in docs}
    _write_doc_lookup_cache(manifest_mtime, docs)
    return {key: value.model_copy() for key, value in doc_lookup.items()}
def ensure_dirs() -> None:
    for p in (DATA_RAW, DATA_PROCESSED, DATA_SNAPSHOTS, UPLOADS_DIR):
        p.mkdir(parents=True, exist_ok=True)


def normalize_text(text: str) -> str:
    return "\n".join([line.rstrip() for line in text.replace("\r\n", "\n").split("\n")])


def materialize_document(content: str, source_name: str) -> Path:
    ensure_dirs()
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()[:10]
    fname = f"{source_name}-{h}.txt"
    out = DATA_RAW / fname
    out.write_text(content, encoding="utf-8")
    return out


def save_chunks(doc_id: str, chunks: Iterable[Chunk]) -> Path:
    ensure_dirs()
    _initialize_metadata_store()
    chunk_list = list(chunks)
    with _connect_metadata_db() as conn:
        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        conn.executemany(
            """
            INSERT OR REPLACE INTO chunks (
                chunk_id,
                doc_id,
                text,
                start_idx,
                end_idx,
                metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    c.chunk_id,
                    c.doc_id,
                    c.text,
                    c.start_idx,
                    c.end_idx,
                    _json_dumps(c.metadata or {}),
                )
                for c in chunk_list
            ],
        )
        conn.commit()

    payload = []
    for c in chunk_list:
        record = asdict(c)
        meta = dict(record.get("metadata", {}))
        if "highlight_start" in meta:
            meta["highlight_start"] = int(meta["highlight_start"])
        if "highlight_end" in meta:
            meta["highlight_end"] = int(meta["highlight_end"])
        record["metadata"] = meta
        payload.append(record)
    out = DATA_PROCESSED / f"{doc_id}.chunks.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_chunks(doc_id: str) -> List[Chunk]:
    _initialize_metadata_store()
    with _connect_metadata_db() as conn:
        rows = conn.execute(
            """
            SELECT chunk_id, doc_id, text, start_idx, end_idx, metadata
            FROM chunks
            WHERE doc_id = ?
            ORDER BY chunk_id
            """,
            (doc_id,),
        ).fetchall()
    if rows:
        return [
            Chunk(
                doc_id=row["doc_id"],
                chunk_id=row["chunk_id"],
                text=row["text"],
                start_idx=int(row["start_idx"] or 0),
                end_idx=int(row["end_idx"] or 0),
                metadata=_json_loads(row["metadata"], {}),
            )
            for row in rows
        ]
    path = DATA_PROCESSED / f"{doc_id}.chunks.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Chunk(**item) for item in payload]


def _doc_id_from_chunk_id(chunk_id: str) -> str:
    parts = chunk_id.rsplit("-", 2)
    if len(parts) < 3:
        return chunk_id
    return parts[0]


def load_chunk_by_id(chunk_id: str) -> Optional[Chunk]:
    _initialize_metadata_store()
    with _connect_metadata_db() as conn:
        row = conn.execute(
            """
            SELECT chunk_id, doc_id, text, start_idx, end_idx, metadata
            FROM chunks
            WHERE chunk_id = ?
            """,
            (chunk_id,),
        ).fetchone()
    if row is not None:
        return Chunk(
            doc_id=row["doc_id"],
            chunk_id=row["chunk_id"],
            text=row["text"],
            start_idx=int(row["start_idx"] or 0),
            end_idx=int(row["end_idx"] or 0),
            metadata=_json_loads(row["metadata"], {}),
        )
    doc_id = _doc_id_from_chunk_id(chunk_id)
    chunk = _load_chunk_from_doc(doc_id, chunk_id)
    if chunk is not None:
        return chunk
    # Fallback scan in case chunk_id does not follow the standard pattern
    for path in DATA_PROCESSED.glob("*.chunks.json"):
        fallback_doc_id = path.stem
        chunk = _load_chunk_from_doc(fallback_doc_id, chunk_id)
        if chunk is not None:
            return chunk
    return None


def _load_chunk_from_doc(doc_id: str, chunk_id: str) -> Optional[Chunk]:
    for chunk in load_chunks(doc_id):
        if chunk.chunk_id == chunk_id:
            return chunk
    return None


def load_manifest() -> List[Document]:
    ensure_dirs()
    _initialize_metadata_store()
    global _MANIFEST_CACHE, _MANIFEST_MTIME
    mtime = _metadata_mtime()
    if mtime is None:
        _MANIFEST_CACHE = []
        _MANIFEST_MTIME = None
        return []
    if _MANIFEST_CACHE is not None and _MANIFEST_MTIME == mtime:
        return [doc.model_copy() for doc in _MANIFEST_CACHE]
    with _connect_metadata_db() as conn:
        rows = conn.execute(
            """
            SELECT doc_id, source_name, language, url, domain, freshness, checksum, version, updated_at, tags, extra
            FROM documents
            ORDER BY updated_at DESC
            """
        ).fetchall()
    docs: List[Document] = []
    for row in rows:
        docs.append(
            Document(
                doc_id=row["doc_id"],
                source_name=row["source_name"],
                language=row["language"] or "auto",
                url=row["url"],
                domain=row["domain"],
                freshness=row["freshness"],
                checksum=row["checksum"],
                version=int(row["version"] or 1),
                updated_at=_parse_datetime(row["updated_at"]),
                tags=_json_loads(row["tags"], []),
                extra=_json_loads(row["extra"], {}),
            )
        )
    _MANIFEST_CACHE = docs
    _MANIFEST_MTIME = mtime
    return [doc.model_copy() for doc in docs]


def _upload_meta_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}.json"


def save_upload_file(
    filename: str,
    content: bytes,
    *,
    mime_type: str,
    purpose: str = "chat",
    uploader: str | None = None,
    retention_days: int | None = None,
) -> UploadRecord:
    ensure_dirs()
    upload_id = uuid.uuid4().hex
    suffix = Path(filename).suffix.lower()
    storage_filename = f"{upload_id}{suffix}" if suffix else upload_id
    storage_path = UPLOADS_DIR / storage_filename
    storage_path.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()
    stored_at = datetime.now(UTC)
    expires_at = None
    if retention_days is not None and retention_days > 0:
        expires_at = stored_at + timedelta(days=retention_days)
    record = UploadRecord(
        upload_id=upload_id,
        filename=filename,
        storage_filename=storage_filename,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=sha256,
        stored_at=stored_at,
        purpose=purpose,
        uploader=uploader,
        retention_days=retention_days,
        expires_at=expires_at,
    )
    meta_path = _upload_meta_path(upload_id)
    meta_path.write_text(record.model_dump_json(), encoding="utf-8")
    return record


def load_upload_record(upload_id: str) -> UploadRecord | None:
    meta_path = _upload_meta_path(upload_id)
    if not meta_path.exists():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        return UploadRecord.model_validate(payload)
    except Exception:
        return None


def get_upload_expiry(
    record: UploadRecord,
    *,
    default_retention_days: int | None = None,
) -> datetime | None:
    if record.expires_at:
        return record.expires_at
    if record.retention_days is not None and record.retention_days > 0:
        return record.stored_at + timedelta(days=record.retention_days)
    if default_retention_days is not None and default_retention_days > 0:
        return record.stored_at + timedelta(days=default_retention_days)
    return None


def is_upload_expired(
    record: UploadRecord,
    *,
    now: datetime | None = None,
    default_retention_days: int | None = None,
) -> bool:
    expires_at = get_upload_expiry(record, default_retention_days=default_retention_days)
    if not expires_at:
        return False
    now = now or datetime.now(UTC)
    return expires_at <= now


def list_upload_records() -> List[UploadRecord]:
    ensure_dirs()
    records: List[UploadRecord] = []
    for meta_path in UPLOADS_DIR.glob("*.json"):
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            record = UploadRecord.model_validate(payload)
        except Exception:
            continue
        records.append(record)
    return records


def delete_upload(upload_id: str) -> bool:
    ensure_dirs()
    record = load_upload_record(upload_id)
    removed = False
    meta_path = _upload_meta_path(upload_id)
    if meta_path.exists():
        meta_path.unlink(missing_ok=True)
        removed = True
    if record is None:
        return removed
    storage_path = UPLOADS_DIR / record.storage_filename
    if storage_path.exists():
        storage_path.unlink(missing_ok=True)
        removed = True
    return removed


def purge_expired_uploads(
    *,
    now: datetime | None = None,
    default_retention_days: int | None = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    ensure_dirs()
    now = now or datetime.now(UTC)
    expired_ids: List[str] = []
    skipped = 0
    for record in list_upload_records():
        if not is_upload_expired(record, now=now, default_retention_days=default_retention_days):
            skipped += 1
            continue
        expired_ids.append(record.upload_id)
        if not dry_run:
            delete_upload(record.upload_id)
    return {
        "deleted": 0 if dry_run else len(expired_ids),
        "skipped": skipped,
        "expired_ids": expired_ids,
    }


def save_manifest(documents: Iterable[Document]) -> Path:
    ensure_dirs()
    _initialize_metadata_store()
    docs = [Document.model_validate(doc) if not isinstance(doc, Document) else doc for doc in documents]
    doc_ids = {doc.doc_id for doc in docs}
    with _connect_metadata_db() as conn:
        existing_ids = {
            row["doc_id"]
            for row in conn.execute("SELECT doc_id FROM documents").fetchall()
        }
        to_delete = existing_ids - doc_ids
        if to_delete:
            conn.executemany("DELETE FROM documents WHERE doc_id = ?", [(doc_id,) for doc_id in to_delete])
        conn.executemany(
            """
            INSERT OR REPLACE INTO documents (
                doc_id,
                source_name,
                language,
                url,
                domain,
                freshness,
                checksum,
                version,
                updated_at,
                tags,
                extra
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    doc.doc_id,
                    doc.source_name,
                    doc.language,
                    doc.url,
                    doc.domain,
                    doc.freshness,
                    doc.checksum,
                    int(doc.version),
                    doc.updated_at.isoformat(),
                    _json_dumps(doc.tags or []),
                    _json_dumps(doc.extra or {}),
                )
                for doc in docs
            ],
        )
        conn.commit()

    serialized = [doc.model_dump(mode="json") for doc in docs]
    MANIFEST_PATH.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
    global _MANIFEST_CACHE, _MANIFEST_MTIME
    _MANIFEST_CACHE = docs
    _MANIFEST_MTIME = _metadata_mtime()
    if _MANIFEST_MTIME is not None:
        try:
            _write_doc_lookup_cache(_MANIFEST_MTIME, docs)
        except Exception:
            pass
    return MANIFEST_PATH


def load_slots_config() -> List[Dict[str, Any]]:
    ensure_dirs()
    if not SLOTS_PATH.exists():
        return []
    return json.loads(SLOTS_PATH.read_text(encoding="utf-8"))


def save_slots_config(payload: Iterable[Dict[str, Any]]) -> Path:
    ensure_dirs()
    data = list(payload)
    SLOTS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return SLOTS_PATH


def load_retrieval_settings() -> Dict[str, Any]:
    ensure_dirs()
    if not RETRIEVAL_SETTINGS_PATH.exists():
        return {}
    return json.loads(RETRIEVAL_SETTINGS_PATH.read_text(encoding="utf-8"))


def save_retrieval_settings(settings: Dict[str, Any]) -> Path:
    ensure_dirs()
    RETRIEVAL_SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return RETRIEVAL_SETTINGS_PATH


def _normalize_assistant_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    profile = {
        "name": DEFAULT_ASSISTANT_PROFILE["name"],
        "avatar": dict(DEFAULT_ASSISTANT_PROFILE["avatar"]),
    }
    if not isinstance(payload, dict):
        return profile
    raw_profile = payload.get("profile")
    if isinstance(raw_profile, dict):
        payload = raw_profile
    name = str(payload.get("name") or "").strip()
    if name:
        profile["name"] = name
    avatar = payload.get("avatar")
    if isinstance(avatar, dict):
        for key in profile["avatar"]:
            value = avatar.get(key)
            if key == "image_url":
                if value is None:
                    profile["avatar"][key] = None
                    continue
                cleaned = str(value).strip()
                profile["avatar"][key] = cleaned or None
                continue
            if value is None:
                continue
            cleaned = str(value).strip()
            if cleaned:
                profile["avatar"][key] = cleaned
    return profile


def load_assistant_profile_record() -> Dict[str, Any]:
    ensure_dirs()
    if not ASSISTANT_PROFILE_PATH.exists():
        return {"profile": _normalize_assistant_profile({}), "updated_at": None}
    try:
        payload = json.loads(ASSISTANT_PROFILE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"profile": _normalize_assistant_profile({}), "updated_at": None}
    profile = _normalize_assistant_profile(payload if isinstance(payload, dict) else {})
    updated_at = payload.get("updated_at") if isinstance(payload, dict) else None
    return {"profile": profile, "updated_at": updated_at}


def load_assistant_profile() -> Dict[str, Any]:
    return load_assistant_profile_record()["profile"]


def save_assistant_profile_record(profile: Dict[str, Any]) -> Dict[str, Any]:
    ensure_dirs()
    normalized = _normalize_assistant_profile(profile)
    updated_at = datetime.now(UTC).isoformat()
    record = dict(normalized)
    record["updated_at"] = updated_at
    ASSISTANT_PROFILE_PATH.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"profile": normalized, "updated_at": updated_at}


def serialize_slot_definition(slot: SlotDefinition) -> Dict[str, Any]:
    return {
        "name": slot.name,
        "description": slot.description,
        "prompt": slot.prompt,
        "prompt_zh": getattr(slot, "prompt_zh", None),
        "required": slot.required,
        "value_type": slot.value_type,
        "choices": slot.choices,
        "min_value": slot.min_value,
        "max_value": slot.max_value,
    }


def append_audit_log(entry: Dict[str, Any]) -> Path:
    ensure_dirs()
    payload = dict(entry)
    payload.setdefault("timestamp", datetime.now(UTC).isoformat())
    line = json.dumps(payload, ensure_ascii=False)
    if AUDIT_LOG_PATH.exists():
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    else:
        AUDIT_LOG_PATH.write_text(line + "\n", encoding="utf-8")
    return AUDIT_LOG_PATH


def read_audit_logs(limit: int | None = None) -> List[Dict[str, Any]]:
    ensure_dirs()
    if not AUDIT_LOG_PATH.exists():
        return []
    entries: List[Dict[str, Any]] = []
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()
    if limit is not None and limit > 0:
        lines = lines[-limit:]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            entries.append(record)
        except json.JSONDecodeError:
            continue
    entries.reverse()
    return entries


def delete_document(doc_id: str) -> bool:
    docs = {doc.doc_id: doc for doc in load_manifest()}
    if doc_id not in docs:
        return False

    docs.pop(doc_id, None)
    save_manifest(docs.values())

    chunk_file = DATA_PROCESSED / f"{doc_id}.chunks.json"
    if chunk_file.exists():
        chunk_file.unlink()

    for raw_file in DATA_RAW.glob(f"{doc_id}*"):
        try:
            raw_file.unlink()
        except OSError:
            continue

    return True


def mark_document_verified(doc_id: str, *, verified_at: datetime | None = None, actor: str | None = None) -> Document | None:
    """Mark a document as manually verified (CIT-3).

    Stores ISO timestamp in Document.extra['verified_at'] and optional actor in ['verified_by'].
    """

    docs = {doc.doc_id: doc for doc in load_manifest()}
    doc = docs.get(doc_id)
    if not doc:
        return None
    now = verified_at or datetime.now(UTC)
    extra = dict(doc.extra or {})
    extra["verified_at"] = now.isoformat()
    if actor:
        extra["verified_by"] = actor
    doc.extra = extra
    doc.updated_at = now
    docs[doc_id] = doc
    save_manifest(docs.values())
    return doc


def upsert_document(document: Document) -> Document:
    docs = {doc.doc_id: doc for doc in load_manifest()}
    existing = docs.get(document.doc_id)
    if existing:
        document.version = existing.version + 1
    document.updated_at = datetime.now(UTC)
    docs[document.doc_id] = document
    save_manifest(docs.values())
    return document


def get_document(doc_id: str) -> Optional[Document]:
    for doc in load_manifest():
        if doc.doc_id == doc_id:
            return doc
    return None


def create_snapshot(version_note: str = "v1") -> Path:
    ensure_dirs()
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    snap_dir = DATA_SNAPSHOTS / f"{ts}_{version_note}"
    snap_dir.mkdir(parents=True, exist_ok=True)
    # copy processed artifacts
    for f in DATA_PROCESSED.glob("*.json"):
        shutil.copy2(f, snap_dir / f.name)
    metadata_db = _metadata_db_path()
    if metadata_db.exists():
        shutil.copy2(metadata_db, snap_dir / metadata_db.name)
    return snap_dir


def load_stop_list() -> List[str]:
    ensure_dirs()
    if not STOP_LIST_PATH.exists():
        return []
    payload = json.loads(STOP_LIST_PATH.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [str(item) for item in payload]
    return []


def save_stop_list(items: Iterable[str]) -> Path:
    ensure_dirs()
    payload = [str(item).strip() for item in items if str(item).strip()]
    STOP_LIST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return STOP_LIST_PATH


def save_assistant_avatar(content: bytes, *, mime_type: str) -> Dict[str, Any]:
    ensure_dirs()
    ext = ASSISTANT_AVATAR_MIME.get((mime_type or "").lower())
    if not ext:
        raise ValueError("Unsupported avatar mime type")
    for existing in UPLOADS_DIR.glob(f"{ASSISTANT_AVATAR_PREFIX}.*"):
        try:
            existing.unlink()
        except OSError:
            continue
    filename = f"{ASSISTANT_AVATAR_PREFIX}.{ext}"
    path = UPLOADS_DIR / filename
    path.write_bytes(content)
    updated_at = datetime.now(UTC).isoformat()
    return {"filename": filename, "url": f"/uploads/{filename}", "updated_at": updated_at}


def load_escalations(limit: int | None = None) -> List[Dict[str, Any]]:
    ensure_dirs()
    with _ESCALATIONS_LOCK:
        if not ESCALATIONS_PATH.exists():
            return []
        try:
            records = json.loads(ESCALATIONS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(records, list):
            return []
        records.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        if limit is not None:
            return records[:limit]
        return records


def append_escalation(entry: Dict[str, Any]) -> Dict[str, Any]:
    ensure_dirs()
    with _ESCALATIONS_LOCK:
        records = load_escalations()
        payload = dict(entry)
        payload.setdefault("escalation_id", uuid.uuid4().hex)
        payload.setdefault("status", "pending")
        payload.setdefault("created_at", datetime.now(UTC).isoformat())
        records.insert(0, payload)
        ESCALATIONS_PATH.write_text(
            json.dumps(records[:500], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return payload


def load_jobs_history(limit: int | None = None) -> List[Dict[str, Any]]:
    ensure_dirs()
    with _JOB_HISTORY_LOCK:
        if not JOBS_PATH.exists():
            return []
        try:
            records = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        if not isinstance(records, list):
            return []
        records.sort(key=lambda item: item.get("started_at", ""), reverse=True)
        if limit and limit > 0:
            return records[:limit]
        return records


def append_job_history(entry: Dict[str, Any]) -> Path:
    ensure_dirs()
    with _JOB_HISTORY_LOCK:
        records = load_jobs_history()
        payload = dict(entry)
        payload.setdefault("job_id", uuid.uuid4().hex)
        payload.setdefault("started_at", datetime.now(UTC).isoformat())
        records.insert(0, payload)
        JOBS_PATH.write_text(json.dumps(records[:500], ensure_ascii=False, indent=2), encoding="utf-8")
        return JOBS_PATH


def update_job_history(job_id: str, updates: Dict[str, Any]) -> bool:
    ensure_dirs()
    with _JOB_HISTORY_LOCK:
        records = load_jobs_history()
        updated = False
        for idx, record in enumerate(records):
            if record.get("job_id") == job_id:
                record.update(updates)
                records[idx] = record
                updated = True
                break
        if not updated:
            return False
        JOBS_PATH.write_text(json.dumps(records[:500], ensure_ascii=False, indent=2), encoding="utf-8")
        return True


def _prune_history_table(conn: sqlite3.Connection, table: str, max_entries: int) -> None:
    if max_entries <= 0:
        return
    conn.execute(
        f"""
        DELETE FROM {table}
        WHERE id NOT IN (
            SELECT id FROM {table}
            ORDER BY id DESC
            LIMIT ?
        )
        """,
        (max_entries,),
    )


def _load_latest_metrics_entry(conn: sqlite3.Connection) -> Dict[str, Any] | None:
    row = conn.execute(
        "SELECT timestamp, snapshot_json FROM metrics_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return {"timestamp": row["timestamp"], "snapshot": _json_loads(row["snapshot_json"], {})}


def _load_latest_status_entry(conn: sqlite3.Connection) -> Dict[str, Any] | None:
    row = conn.execute(
        "SELECT timestamp, status_json FROM status_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    return {"timestamp": row["timestamp"], "status": _json_loads(row["status_json"], {})}


def append_metrics_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    ensure_dirs()
    _initialize_metadata_store()
    now = datetime.now(UTC)
    entry = {
        "timestamp": now.isoformat(),
        "snapshot": snapshot,
    }
    with _METRICS_HISTORY_LOCK:
        with _connect_metadata_db() as conn:
            latest = _load_latest_metrics_entry(conn)
            if latest:
                last_ts = _parse_datetime(latest["timestamp"])
                if (now - last_ts).total_seconds() < METRICS_SNAPSHOT_MIN_INTERVAL_SECONDS:
                    return latest
            conn.execute(
                "INSERT INTO metrics_snapshots (timestamp, snapshot_json) VALUES (?, ?)",
                (entry["timestamp"], _json_dumps(snapshot)),
            )
            _prune_history_table(conn, "metrics_snapshots", METRICS_HISTORY_MAX)
            conn.commit()
    return entry


def load_metrics_history(limit: int | None = None) -> List[Dict[str, Any]]:
    ensure_dirs()
    _initialize_metadata_store()
    with _METRICS_HISTORY_LOCK:
        with _connect_metadata_db() as conn:
            if limit is not None and limit > 0:
                rows = conn.execute(
                    "SELECT timestamp, snapshot_json FROM metrics_snapshots ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                rows.reverse()
            else:
                rows = conn.execute(
                    "SELECT timestamp, snapshot_json FROM metrics_snapshots ORDER BY id ASC"
                ).fetchall()
    return [
        {"timestamp": row["timestamp"], "snapshot": _json_loads(row["snapshot_json"], {})}
        for row in rows
    ]


def append_status_snapshot(status_payload: Dict[str, Any]) -> Dict[str, Any]:
    ensure_dirs()
    _initialize_metadata_store()
    now = datetime.now(UTC)
    entry = {
        "timestamp": now.isoformat(),
        "status": status_payload,
    }
    with _STATUS_HISTORY_LOCK:
        with _connect_metadata_db() as conn:
            latest = _load_latest_status_entry(conn)
            if latest:
                last_ts = _parse_datetime(latest["timestamp"])
                if (now - last_ts).total_seconds() < STATUS_SNAPSHOT_MIN_INTERVAL_SECONDS:
                    return latest
            conn.execute(
                "INSERT INTO status_snapshots (timestamp, status_json) VALUES (?, ?)",
                (entry["timestamp"], _json_dumps(status_payload)),
            )
            _prune_history_table(conn, "status_snapshots", STATUS_HISTORY_MAX)
            conn.commit()
    return entry


def load_status_history(limit: int | None = None) -> List[Dict[str, Any]]:
    ensure_dirs()
    _initialize_metadata_store()
    with _STATUS_HISTORY_LOCK:
        with _connect_metadata_db() as conn:
            if limit is not None and limit > 0:
                rows = conn.execute(
                    "SELECT timestamp, status_json FROM status_snapshots ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                rows.reverse()
            else:
                rows = conn.execute(
                    "SELECT timestamp, status_json FROM status_snapshots ORDER BY id ASC"
                ).fetchall()
    return [
        {"timestamp": row["timestamp"], "status": _json_loads(row["status_json"], {})}
        for row in rows
    ]


def load_templates() -> List[Dict[str, Any]]:
    ensure_dirs()
    if not TEMPLATES_PATH.exists():
        return []
    try:
        records = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(records, list):
        return []
    return records


def get_template(template_id: str) -> Dict[str, Any] | None:
    records = load_templates()
    for record in records:
        if record.get("template_id") == template_id:
            return dict(record)
    return None


def save_templates(records: Iterable[Dict[str, Any]]) -> Path:
    ensure_dirs()
    payload = list(records)
    TEMPLATES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return TEMPLATES_PATH


def upsert_template(entry: Dict[str, Any]) -> Dict[str, Any]:
    records = load_templates()
    template_id = str(entry.get("template_id"))
    now = datetime.now(UTC).isoformat()
    new_record = dict(entry)
    new_record["template_id"] = template_id
    new_record.setdefault("created_at", now)
    new_record["updated_at"] = now
    filtered = [record for record in records if record.get("template_id") != template_id]
    filtered.insert(0, new_record)
    save_templates(filtered[:200])
    return new_record


def delete_template(template_id: str) -> bool:
    records = load_templates()
    filtered = [record for record in records if record.get("template_id") != template_id]
    if len(filtered) == len(records):
        return False
    save_templates(filtered)
    return True


def load_prompts() -> List[Dict[str, Any]]:
    ensure_dirs()
    global _PROMPTS_CACHE, _PROMPTS_MTIME
    if not PROMPTS_PATH.exists():
        _PROMPTS_CACHE = []
        _PROMPTS_MTIME = None
        return []
    mtime = PROMPTS_PATH.stat().st_mtime
    if _PROMPTS_CACHE is not None and _PROMPTS_MTIME == mtime:
        return [dict(record) for record in _PROMPTS_CACHE]
    try:
        records = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        records = []
    if not isinstance(records, list):
        records = []
    _PROMPTS_CACHE = [dict(record) for record in records]
    _PROMPTS_MTIME = mtime
    return [dict(record) for record in _PROMPTS_CACHE]


def save_prompts(records: Iterable[Dict[str, Any]]) -> Path:
    ensure_dirs()
    payload = [dict(record) for record in records]
    PROMPTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    global _PROMPTS_CACHE, _PROMPTS_MTIME
    _PROMPTS_CACHE = [dict(record) for record in payload]
    _PROMPTS_MTIME = PROMPTS_PATH.stat().st_mtime if PROMPTS_PATH.exists() else None
    return PROMPTS_PATH


def _slugify_prompt_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return slug or "prompt"


def _ensure_unique_prompt_id(base: str, existing_ids: set[str]) -> str:
    if base not in existing_ids:
        return base
    counter = 2
    candidate = f"{base}_{counter}"
    while candidate in existing_ids:
        counter += 1
        candidate = f"{base}_{counter}"
    return candidate


def upsert_prompt(entry: Dict[str, Any]) -> Dict[str, Any]:
    records = load_prompts()
    prompt_id = str(entry.get("prompt_id") or "").strip()
    now = datetime.now(UTC).isoformat()
    new_record = dict(entry)
    name = str(new_record.get("name") or "").strip()
    language = str(new_record.get("language") or "en").strip() or "en"
    if not prompt_id:
        base = f"{_slugify_prompt_id(name)}_{language.lower().split('-')[0]}"
        existing_ids = {str(record.get("prompt_id")) for record in records if record.get("prompt_id")}
        prompt_id = _ensure_unique_prompt_id(base, existing_ids)
    new_record["prompt_id"] = prompt_id
    new_record.setdefault("created_at", now)
    new_record["updated_at"] = now
    language = new_record.get("language", "en")
    is_active = bool(new_record.get("is_active", False))
    if is_active:
        for record in records:
            if record.get("language", "en") == language:
                record["is_active"] = False
    new_record["is_active"] = is_active
    filtered = [record for record in records if record.get("prompt_id") != prompt_id]
    filtered.insert(0, new_record)
    save_prompts(filtered[:100])
    return new_record


def delete_prompt(prompt_id: str) -> bool:
    records = load_prompts()
    filtered = [record for record in records if record.get("prompt_id") != prompt_id]
    if len(filtered) == len(records):
        return False
    save_prompts(filtered)
    return True


def get_active_prompt(language: str | None = None) -> Dict[str, Any] | None:
    records = load_prompts()
    language = (language or "en").split("-")[0]
    for record in records:
        if record.get("is_active") and record.get("language", "en").startswith(language):
            return record
    for record in records:
        if record.get("language", "en").startswith(language):
            return record
    return None


def set_active_prompt(prompt_id: str) -> Dict[str, Any] | None:
    records = load_prompts()
    target = None
    for record in records:
        if record.get("prompt_id") == prompt_id:
            target = record
            break
    if target is None:
        return None
    language = target.get("language", "en")
    for record in records:
        if record is target:
            record["is_active"] = True
            record["updated_at"] = datetime.now(UTC).isoformat()
        elif record.get("language", "en") == language:
            record["is_active"] = False
    save_prompts(records)
    return target
