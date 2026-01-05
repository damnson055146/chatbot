from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Empty, Queue
from threading import Event, RLock, Thread
from typing import Any, Dict, List

from fastapi import HTTPException

from src.pipelines.ingest import ingest_content
from src.schemas.models import AdminIngestUploadRequest, IngestResponse, JobEnqueueResponse
from src.utils.index_manager import get_index_manager
from src.utils.logging import get_logger
from src.utils.storage import (
    DATA_PROCESSED,
    UPLOADS_DIR,
    append_audit_log,
    append_job_history,
    ensure_dirs,
    is_upload_expired,
    load_upload_record,
    update_job_history,
)
from src.utils.text_extract import extract_text_from_bytes

log = get_logger(__name__)


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(0.0, value)


DEFAULT_MAX_ATTEMPTS = _read_int_env("INGEST_JOB_MAX_ATTEMPTS", 3)
DEFAULT_BACKOFF_SECONDS = _read_float_env("INGEST_JOB_BACKOFF_SECONDS", 2.0)
MAX_BACKOFF_SECONDS = 30.0
DEFAULT_UPLOAD_RETENTION_DAYS = _read_int_env("UPLOAD_RETENTION_DAYS", 30)
INGEST_QUEUE_PATH = DATA_PROCESSED / "ingest_queue.json"
_QUEUE_LOCK = RLock()


def _backoff_seconds(attempt: int) -> float:
    if attempt <= 1:
        return DEFAULT_BACKOFF_SECONDS
    return min(DEFAULT_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)


def ingest_upload_payload(
    payload: AdminIngestUploadRequest,
    *,
    actor: str,
    audit: bool,
) -> IngestResponse:
    if payload.url:
        raise HTTPException(status_code=400, detail="URL ingestion is not supported; upload documents instead")
    record = load_upload_record(payload.upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    if record.purpose != "rag":
        raise HTTPException(status_code=400, detail="Upload is not eligible for knowledge base ingestion")
    if is_upload_expired(record, default_retention_days=DEFAULT_UPLOAD_RETENTION_DAYS):
        raise HTTPException(status_code=410, detail="Upload has expired")

    upload_path = UPLOADS_DIR / record.storage_filename
    if not upload_path.exists():
        raise HTTPException(status_code=404, detail="Upload file missing on disk")

    content_bytes = upload_path.read_bytes()
    extracted = extract_text_from_bytes(
        content=content_bytes,
        mime_type=record.mime_type,
        filename=record.filename,
    )

    result = ingest_content(
        extracted.text,
        source_name=payload.source_name or record.filename,
        doc_id=payload.doc_id or record.upload_id,
        language=payload.language,
        domain=payload.domain,
        freshness=payload.freshness,
        url=payload.url,
        tags=payload.tags,
        extra={
            "upload_id": record.upload_id,
            "upload_filename": record.filename,
            "upload_mime_type": record.mime_type,
            "upload_sha256": record.sha256,
            "upload_uploader": record.uploader or actor,
            **extracted.metadata,
        },
        max_chars=payload.max_chars,
        overlap=payload.overlap,
    )

    manager = get_index_manager()
    manager.rebuild()
    health = manager.health()

    if audit:
        append_audit_log(
            {
                "action": "admin_ingest_upload",
                "upload_id": record.upload_id,
                "doc_id": result.document.doc_id,
                "chunk_count": result.chunk_count,
                "actor": actor,
            }
        )

    return IngestResponse(
        doc_id=result.document.doc_id,
        version=result.document.version,
        chunk_count=result.chunk_count,
        health=health,
    )


@dataclass
class UploadIngestJob:
    job_id: str
    payload: AdminIngestUploadRequest
    actor: str
    audit: bool
    queued_at: datetime
    attempts: int = 0
    max_attempts: int = DEFAULT_MAX_ATTEMPTS


def _job_record(job: UploadIngestJob) -> Dict[str, Any]:
    return {
        "job_id": job.job_id,
        "payload": job.payload.model_dump(mode="json"),
        "actor": job.actor,
        "audit": job.audit,
        "queued_at": job.queued_at.isoformat(),
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
    }


def _load_queue_records() -> List[Dict[str, Any]]:
    ensure_dirs()
    if not INGEST_QUEUE_PATH.exists():
        return []
    try:
        payload = json.loads(INGEST_QUEUE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _write_queue_records(records: List[Dict[str, Any]]) -> None:
    ensure_dirs()
    tmp_path = INGEST_QUEUE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(records, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp_path.replace(INGEST_QUEUE_PATH)


def _persist_job(job: UploadIngestJob) -> None:
    record = _job_record(job)
    with _QUEUE_LOCK:
        records = _load_queue_records()
        for idx, item in enumerate(records):
            if item.get("job_id") == job.job_id:
                records[idx] = record
                _write_queue_records(records)
                return
        records.append(record)
        _write_queue_records(records)


def _remove_persisted_job(job_id: str) -> None:
    with _QUEUE_LOCK:
        records = _load_queue_records()
        filtered = [item for item in records if item.get("job_id") != job_id]
        if len(filtered) == len(records):
            return
        _write_queue_records(filtered)


def _hydrate_job(record: Dict[str, Any]) -> UploadIngestJob | None:
    payload_raw = record.get("payload")
    if not isinstance(payload_raw, dict):
        return None
    try:
        payload = AdminIngestUploadRequest.model_validate(payload_raw)
    except Exception:
        return None
    job_id = str(record.get("job_id") or uuid.uuid4().hex)
    actor = str(record.get("actor") or "unknown")
    audit = bool(record.get("audit", False))
    attempts = record.get("attempts")
    max_attempts = record.get("max_attempts")
    if not isinstance(attempts, int) or attempts < 0:
        attempts = 0
    if not isinstance(max_attempts, int) or max_attempts < 1:
        max_attempts = DEFAULT_MAX_ATTEMPTS
    queued_at_raw = record.get("queued_at")
    if isinstance(queued_at_raw, str):
        try:
            queued_at = datetime.fromisoformat(queued_at_raw)
        except ValueError:
            queued_at = datetime.now(UTC)
    else:
        queued_at = datetime.now(UTC)
    return UploadIngestJob(
        job_id=job_id,
        payload=payload,
        actor=actor,
        audit=audit,
        queued_at=queued_at,
        attempts=attempts,
        max_attempts=max_attempts,
    )


class IngestJobQueue:
    def __init__(self) -> None:
        self._queue: Queue[UploadIngestJob] = Queue()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._restored = False

    def start(self) -> None:
        if not self._restored:
            self._restore_pending_jobs()
            self._restored = True
        if self._thread and self._thread.is_alive():
            return
        self._thread = Thread(target=self._worker, name="ingest-job-worker", daemon=True)
        self._thread.start()

    def enqueue_upload(
        self,
        payload: AdminIngestUploadRequest,
        *,
        actor: str,
        audit: bool,
        max_attempts: int | None = None,
    ) -> JobEnqueueResponse:
        self.start()
        job_id = uuid.uuid4().hex
        queued_at = datetime.now(UTC)
        max_attempts = max_attempts or DEFAULT_MAX_ATTEMPTS

        append_job_history(
            {
                "job_id": job_id,
                "job_type": "ingest_upload",
                "status": "queued",
                "started_at": queued_at.isoformat(),
                "upload_id": payload.upload_id,
                "doc_id": payload.doc_id,
                "source_name": payload.source_name,
                "language": payload.language,
                "actor": actor,
                "attempts": 0,
                "max_attempts": max_attempts,
            }
        )

        job = UploadIngestJob(
            job_id=job_id,
            payload=payload,
            actor=actor,
            audit=audit,
            queued_at=queued_at,
            attempts=0,
            max_attempts=max_attempts,
        )
        _persist_job(job)
        self._queue.put(job)
        return JobEnqueueResponse(
            job_id=job_id,
            job_type="ingest_upload",
            status="queued",
            queued_at=queued_at,
            attempts=0,
            max_attempts=max_attempts,
        )

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._queue.get(timeout=0.5)
            except Empty:
                continue
            try:
                self._run_job(job)
            finally:
                self._queue.task_done()

    def _run_job(self, job: UploadIngestJob) -> None:
        start = time.perf_counter()
        update_job_history(job.job_id, {"status": "running"})
        try:
            result = ingest_upload_payload(job.payload, actor=job.actor, audit=job.audit)
        except Exception as exc:
            job.attempts += 1
            _persist_job(job)
            if isinstance(exc, HTTPException):
                error_message = str(exc.detail)
            else:
                error_message = str(exc)
            if job.attempts < job.max_attempts:
                update_job_history(
                    job.job_id,
                    {
                        "status": "retrying",
                        "attempts": job.attempts,
                        "error": error_message,
                    },
                )
                sleep_for = _backoff_seconds(job.attempts)
                log.warning(
                    "ingest_job_retry",
                    job_id=job.job_id,
                    attempts=job.attempts,
                    sleep_seconds=sleep_for,
                    error=error_message,
                )
                time.sleep(sleep_for)
                self._queue.put(job)
            else:
                update_job_history(
                    job.job_id,
                    {
                        "status": "failed",
                        "attempts": job.attempts,
                        "error": error_message,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "duration_ms": (time.perf_counter() - start) * 1000,
                    },
                )
                _remove_persisted_job(job.job_id)
                log.error("ingest_job_failed", job_id=job.job_id, error=error_message)
            return

        update_job_history(
            job.job_id,
            {
                "status": "succeeded",
                "completed_at": datetime.now(UTC).isoformat(),
                "duration_ms": (time.perf_counter() - start) * 1000,
                "doc_id": result.doc_id,
                "chunk_count": result.chunk_count,
            },
        )
        _remove_persisted_job(job.job_id)
        log.info(
            "ingest_job_succeeded",
            job_id=job.job_id,
            doc_id=result.doc_id,
            chunk_count=result.chunk_count,
        )

    def _restore_pending_jobs(self) -> None:
        with _QUEUE_LOCK:
            records = _load_queue_records()
        if not records:
            return
        restored = 0
        for record in records:
            job = _hydrate_job(record)
            if job is None:
                continue
            if job.attempts >= job.max_attempts:
                update_job_history(
                    job.job_id,
                    {
                        "status": "failed",
                        "attempts": job.attempts,
                        "error": "Job exceeded max attempts before restart",
                        "completed_at": datetime.now(UTC).isoformat(),
                    },
                )
                _remove_persisted_job(job.job_id)
                continue
            update_job_history(
                job.job_id,
                {
                    "status": "queued",
                    "attempts": job.attempts,
                    "resumed_at": datetime.now(UTC).isoformat(),
                },
            )
            self._queue.put(job)
            restored += 1
        if restored:
            log.info("ingest_job_restore", restored=restored)


_QUEUE: IngestJobQueue | None = None


def get_ingest_queue() -> IngestJobQueue:
    global _QUEUE
    if _QUEUE is None:
        _QUEUE = IngestJobQueue()
    return _QUEUE
