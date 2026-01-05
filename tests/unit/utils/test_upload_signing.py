import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from src.utils import storage
from src.utils.upload_signing import sign_upload_url, verify_upload_signature


def _configure_paths(tmp_path, monkeypatch):
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    snapshots_dir = tmp_path / "snapshots"
    uploads_dir = tmp_path / "uploads"

    monkeypatch.setattr(storage, "DATA_RAW", raw_dir)
    monkeypatch.setattr(storage, "DATA_PROCESSED", processed_dir)
    monkeypatch.setattr(storage, "DATA_SNAPSHOTS", snapshots_dir)
    monkeypatch.setattr(storage, "UPLOADS_DIR", uploads_dir)


def test_sign_upload_url_round_trip():
    signed = sign_upload_url("upload-123", base_path="/v1/upload/upload-123/file", disposition="inline", expires_in=120)
    parsed = urlparse(signed.url)
    params = parse_qs(parsed.query)
    exp = int(params["exp"][0])
    sig = params["sig"][0]
    disposition = params["disposition"][0]

    assert verify_upload_signature("upload-123", exp=exp, sig=sig, disposition=disposition)


def test_verify_upload_signature_rejects_expired():
    expired = int(time.time()) - 5
    assert not verify_upload_signature("upload-123", exp=expired, sig="deadbeef", disposition="inline")


def test_purge_expired_uploads_removes_files(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)
    expired_record = storage.save_upload_file(
        filename="expired.txt",
        content=b"expired",
        mime_type="text/plain",
        retention_days=7,
    )
    active_record = storage.save_upload_file(
        filename="active.txt",
        content=b"active",
        mime_type="text/plain",
        retention_days=7,
    )

    expired_meta = storage.UPLOADS_DIR / f"{expired_record.upload_id}.json"
    expired_payload = json.loads(expired_meta.read_text(encoding="utf-8"))
    expired_payload["expires_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    expired_meta.write_text(json.dumps(expired_payload), encoding="utf-8")

    active_meta = storage.UPLOADS_DIR / f"{active_record.upload_id}.json"
    active_payload = json.loads(active_meta.read_text(encoding="utf-8"))
    active_payload["expires_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    active_meta.write_text(json.dumps(active_payload), encoding="utf-8")

    result = storage.purge_expired_uploads(default_retention_days=30)
    assert result["deleted"] == 1
    assert expired_record.upload_id in result["expired_ids"]
    assert active_record.upload_id not in result["expired_ids"]

    expired_file = storage.UPLOADS_DIR / expired_record.storage_filename
    active_file = storage.UPLOADS_DIR / active_record.storage_filename
    assert not expired_file.exists()
    assert active_file.exists()
