import pytest

from src.pipelines.ingest import ingest_file
from src.utils import storage
from src.utils.observability import get_metrics


@pytest.mark.smoke
def test_ingest_pipeline_updates_manifest(tmp_path, monkeypatch):
    metrics = get_metrics()
    metrics.reset()

    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    snapshots_dir = tmp_path / "snapshots"
    manifest_path = processed_dir / "manifest.json"

    monkeypatch.setattr(storage, "DATA_RAW", raw_dir)
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed_dir)
    monkeypatch.setattr(storage, "DATA_SNAPSHOTS", snapshots_dir)
    monkeypatch.setattr(storage, "MANIFEST_PATH", manifest_path)

    content = "Visa application requirements and document list."
    input_file = tmp_path / "visa.txt"
    input_file.write_text(content, encoding="utf-8")

    result = ingest_file(input_file, domain="visa", tags=["policy", "2024"])

    assert result.chunk_count > 0
    manifest = storage.load_manifest()
    assert len(manifest) == 1
    doc = manifest[0]
    assert doc.doc_id == "visa"
    assert doc.domain == "visa"
    assert "policy" in doc.tags
    assert doc.version == 1

    chunk = storage.load_chunk_by_id(f"{doc.doc_id}-0-0")
    assert chunk is not None
    assert chunk.metadata.get("start_idx") == 0

    # Re-ingest to ensure version bump
    ingest_file(input_file, domain="visa")
    doc = storage.load_manifest()[0]
    assert doc.version == 2

    snapshot = get_metrics().snapshot()
    phases = snapshot.get("phases", {})
    assert "ingest_total" in phases
    assert phases["ingest_total"]["count"] >= 2
    assert "ingest_chunk" in phases

