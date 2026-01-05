import argparse
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.cli import cmd_ingest_bulk
from src.schemas.models import BulkIngestRequest
from src.utils import storage


def _configure_paths(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    snapshots = tmp_path / "snapshots"
    monkeypatch.setattr(storage, "DATA_RAW", raw)
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed)
    monkeypatch.setattr(storage, "DATA_SNAPSHOTS", snapshots)
    monkeypatch.setattr(storage, "MANIFEST_PATH", processed / "manifest.json")
    storage._MANIFEST_CACHE = None
    storage._MANIFEST_MTIME = None
    storage._METADATA_READY = False
    storage._METADATA_READY_PATH = None
    storage.ensure_dirs()


def test_bulk_ingest_manifest_validation():
    with pytest.raises(ValidationError):
        BulkIngestRequest.model_validate({"documents": [{"source_name": "missing"}]})


def test_bulk_ingest_cli_ingests_documents(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)

    file_path = tmp_path / "file_doc.txt"
    file_path.write_text("File-based document content.", encoding="utf-8")

    manifest_payload = {
        "documents": [
            {
                "source_name": "Inline Doc",
                "content": "Inline document content.",
                "doc_id": "inline-doc",
                "tags": ["inline"],
            },
            {
                "source_name": "File Doc",
                "path": "file_doc.txt",
                "doc_id": "file-doc",
                "tags": ["file"],
            },
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    args = argparse.Namespace(
        manifest=str(manifest_path),
        base_dir=str(tmp_path),
        continue_on_error=False,
    )
    cmd_ingest_bulk(args, config={})

    docs = storage.load_manifest()
    doc_ids = {doc.doc_id for doc in docs}
    assert {"inline-doc", "file-doc"} <= doc_ids
    assert storage.load_chunks("inline-doc")
    assert storage.load_chunks("file-doc")
