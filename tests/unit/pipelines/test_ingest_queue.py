import json
from datetime import UTC, datetime

from src.pipelines import ingest_queue
from src.schemas.models import AdminIngestUploadRequest
from src.utils import storage


def _configure_paths(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    snapshots_dir = tmp_path / "snapshots"
    uploads_dir = tmp_path / "uploads"

    monkeypatch.setattr(storage, "DATA_RAW", raw_dir)
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed_dir)
    monkeypatch.setattr(storage, "DATA_SNAPSHOTS", snapshots_dir)
    monkeypatch.setattr(storage, "UPLOADS_DIR", uploads_dir)
    monkeypatch.setattr(storage, "JOBS_PATH", processed_dir / "jobs.json")

    monkeypatch.setattr(ingest_queue, "INGEST_QUEUE_PATH", processed_dir / "ingest_queue.json")


def _find_job(history, job_id):
    for record in history:
        if record.get("job_id") == job_id:
            return record
    return None


def test_restore_pending_jobs_requeues_and_updates_history(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    payload = AdminIngestUploadRequest(upload_id="upload-1")
    job_id = "job-restore"

    storage.append_job_history(
        {
            "job_id": job_id,
            "job_type": "ingest_upload",
            "status": "queued",
            "started_at": datetime.now(UTC).isoformat(),
            "upload_id": payload.upload_id,
        }
    )

    job = ingest_queue.UploadIngestJob(
        job_id=job_id,
        payload=payload,
        actor="tester",
        audit=False,
        queued_at=datetime.now(UTC),
        attempts=1,
        max_attempts=3,
    )
    ingest_queue._write_queue_records([ingest_queue._job_record(job)])

    queue = ingest_queue.IngestJobQueue()
    queue._restore_pending_jobs()

    restored = queue._queue.get_nowait()
    assert restored.job_id == job_id
    assert restored.attempts == 1

    history = storage.load_jobs_history()
    record = _find_job(history, job_id)
    assert record is not None
    assert record["status"] == "queued"
    assert record["attempts"] == 1
    assert "resumed_at" in record

    records = json.loads(ingest_queue.INGEST_QUEUE_PATH.read_text(encoding="utf-8"))
    assert records
    assert records[0]["job_id"] == job_id


def test_restore_pending_jobs_marks_failed_after_max_attempts(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    payload = AdminIngestUploadRequest(upload_id="upload-2")
    job_id = "job-failed"

    storage.append_job_history(
        {
            "job_id": job_id,
            "job_type": "ingest_upload",
            "status": "queued",
            "started_at": datetime.now(UTC).isoformat(),
            "upload_id": payload.upload_id,
        }
    )

    job = ingest_queue.UploadIngestJob(
        job_id=job_id,
        payload=payload,
        actor="tester",
        audit=False,
        queued_at=datetime.now(UTC),
        attempts=3,
        max_attempts=3,
    )
    ingest_queue._write_queue_records([ingest_queue._job_record(job)])

    queue = ingest_queue.IngestJobQueue()
    queue._restore_pending_jobs()

    assert queue._queue.empty()

    records = json.loads(ingest_queue.INGEST_QUEUE_PATH.read_text(encoding="utf-8"))
    assert records == []

    history = storage.load_jobs_history()
    record = _find_job(history, job_id)
    assert record is not None
    assert record["status"] == "failed"
    assert record["attempts"] == 3
    assert record["error"] == "Job exceeded max attempts before restart"
    assert "completed_at" in record
