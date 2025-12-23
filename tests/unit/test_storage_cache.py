from datetime import datetime, UTC

from src.schemas.models import Document
from src.utils import storage


def _configure_paths(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    snapshots = tmp_path / "snapshots"
    monkeypatch.setattr(storage, "DATA_RAW", raw)
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed)
    monkeypatch.setattr(storage, "DATA_SNAPSHOTS", snapshots)
    monkeypatch.setattr(storage, "MANIFEST_PATH", processed / "manifest.json")
    storage.ensure_dirs()
    storage._MANIFEST_CACHE = None
    storage._MANIFEST_MTIME = None


def test_get_doc_lookup_uses_persistent_cache(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)

    docs = [
        Document(doc_id="d1", source_name="Doc One", updated_at=datetime.now(UTC)),
        Document(doc_id="d2", source_name="Doc Two", updated_at=datetime.now(UTC)),
    ]
    storage.save_manifest(docs)

    first_lookup = storage.get_doc_lookup()
    assert set(first_lookup.keys()) == {"d1", "d2"}

    cache_file = (storage.DATA_PROCESSED / "cache" / "doc_lookup.json")
    assert cache_file.exists()

    def fail_load_manifest():  # pragma: no cover - ensuring cache path works
        raise AssertionError("load_manifest should not be invoked when cache is valid")

    original = storage.load_manifest
    monkeypatch.setattr(storage, "load_manifest", fail_load_manifest)
    cached_lookup = storage.get_doc_lookup()
    assert set(cached_lookup.keys()) == {"d1", "d2"}
    monkeypatch.setattr(storage, "load_manifest", original)

    new_docs = [
        Document(doc_id="d3", source_name="Doc Three", updated_at=datetime.now(UTC)),
    ]
    storage.save_manifest(new_docs)

    refreshed_lookup = storage.get_doc_lookup()
    assert set(refreshed_lookup.keys()) == {"d3"}
