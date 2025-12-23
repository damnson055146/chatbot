from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.schemas.models import Document, UploadRecord
from src.schemas.slots import SlotDefinition

from .chunking import Chunk

DATA_RAW = Path("assets/data/raw")
DATA_PROCESSED = Path("assets/data/processed")
DATA_SNAPSHOTS = Path("assets/data/snapshots")
UPLOADS_DIR = Path("assets/uploads")
MANIFEST_PATH = DATA_PROCESSED / "manifest.json"
SLOTS_PATH = DATA_PROCESSED / "slots.json"
RETRIEVAL_SETTINGS_PATH = DATA_PROCESSED / "retrieval.json"
AUDIT_LOG_PATH = DATA_PROCESSED / "audit.log"
STOP_LIST_PATH = DATA_PROCESSED / "stop_list.json"
JOBS_PATH = DATA_PROCESSED / "jobs.json"
TEMPLATES_PATH = DATA_PROCESSED / "templates.json"
PROMPTS_PATH = DATA_PROCESSED / "prompts.json"


_MANIFEST_CACHE: Optional[List[Document]] = None
_MANIFEST_MTIME: Optional[float] = None
_PROMPTS_CACHE: Optional[List[Dict[str, Any]]] = None
_PROMPTS_MTIME: Optional[float] = None




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
    if not MANIFEST_PATH.exists():
        return {}
    manifest_mtime = MANIFEST_PATH.stat().st_mtime
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
    payload = []
    for c in chunks:
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
    global _MANIFEST_CACHE, _MANIFEST_MTIME
    if not MANIFEST_PATH.exists():
        _MANIFEST_CACHE = []
        _MANIFEST_MTIME = None
        return []
    mtime = MANIFEST_PATH.stat().st_mtime
    if _MANIFEST_CACHE is not None and _MANIFEST_MTIME == mtime:
        return [doc.model_copy() for doc in _MANIFEST_CACHE]
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    docs = [Document.model_validate(item) for item in payload]
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
) -> UploadRecord:
    ensure_dirs()
    upload_id = uuid.uuid4().hex
    suffix = Path(filename).suffix.lower()
    storage_filename = f"{upload_id}{suffix}" if suffix else upload_id
    storage_path = UPLOADS_DIR / storage_filename
    storage_path.write_bytes(content)
    sha256 = hashlib.sha256(content).hexdigest()
    record = UploadRecord(
        upload_id=upload_id,
        filename=filename,
        storage_filename=storage_filename,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=sha256,
        purpose=purpose,
        uploader=uploader,
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


def save_manifest(documents: Iterable[Document]) -> Path:
    ensure_dirs()
    docs = [Document.model_validate(doc) if not isinstance(doc, Document) else doc for doc in documents]
    serialized = [doc.model_dump(mode="json") for doc in docs]
    MANIFEST_PATH.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")
    global _MANIFEST_CACHE, _MANIFEST_MTIME
    _MANIFEST_CACHE = docs
    _MANIFEST_MTIME = MANIFEST_PATH.stat().st_mtime if MANIFEST_PATH.exists() else None
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


def load_jobs_history(limit: int | None = None) -> List[Dict[str, Any]]:
    ensure_dirs()
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
    records = load_jobs_history()
    payload = dict(entry)
    payload.setdefault("job_id", uuid.uuid4().hex)
    payload.setdefault("started_at", datetime.now(UTC).isoformat())
    records.insert(0, payload)
    JOBS_PATH.write_text(json.dumps(records[:500], ensure_ascii=False, indent=2), encoding="utf-8")
    return JOBS_PATH


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


def upsert_prompt(entry: Dict[str, Any]) -> Dict[str, Any]:
    records = load_prompts()
    prompt_id = str(entry.get("prompt_id"))
    now = datetime.now(UTC).isoformat()
    new_record = dict(entry)
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

