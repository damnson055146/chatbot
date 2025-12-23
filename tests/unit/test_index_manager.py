import pytest

from src.pipelines.ingest import ingest_file
from src.utils import index_manager
from src.utils.index_manager import IndexManager
from src.utils import storage


@pytest.mark.smoke
def test_index_manager_rebuilds_and_reports_health(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    snapshots_dir = tmp_path / "snapshots"
    manifest_path = processed_dir / "manifest.json"
    jobs_path = processed_dir / "jobs.json"

    monkeypatch.setattr(storage, "DATA_RAW", raw_dir)
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed_dir)
    monkeypatch.setattr(storage, "DATA_SNAPSHOTS", snapshots_dir)
    monkeypatch.setattr(storage, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(storage, "JOBS_PATH", jobs_path)
    monkeypatch.setattr(index_manager, "DATA_PROCESSED", processed_dir)

    content = "Student visa application requires bank statements and passport copies."
    input_file = tmp_path / "visa.txt"
    input_file.write_text(content, encoding="utf-8")
    ingest_file(input_file, domain="visa")

    manager = IndexManager()
    manager.rebuild()
    manager.configure(alpha=0.7)
    health = manager.health()

    history = storage.load_jobs_history()
    rebuild_jobs = [job for job in history if job.get("job_type") == "index_rebuild"]
    assert rebuild_jobs
    assert rebuild_jobs[0].get("duration_ms") and rebuild_jobs[0]["duration_ms"] > 0

    assert health.document_count == 1
    assert health.chunk_count > 0
    assert health.last_build_at is not None

    results = manager.query("What documents are required?", top_k=1)
    assert results
    assert "passport" in results[0].text

