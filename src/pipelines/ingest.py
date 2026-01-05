from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.schemas.models import Document
from src.utils.chunking import simple_paragraph_chunk
from src.utils.logging import get_logger
from src.utils.observability import get_metrics, time_phase, time_phase_endpoint
from src.utils.storage import (
    ensure_dirs,
    materialize_document,
    normalize_text,
    save_chunks,
    upsert_document,
    append_job_history,
)

log = get_logger(__name__)


@dataclass
class IngestResult:
    document: Document
    chunk_count: int
    raw_path: Path
    chunk_path: Path


def _sanitize_doc_id(value: str) -> str:
    cleaned = "-".join(value.strip().split())
    return cleaned.lower()


def ingest_content(
    content: str,
    *,
    source_name: str,
    doc_id: Optional[str] = None,
    language: str = "auto",
    domain: Optional[str] = None,
    freshness: Optional[str] = None,
    url: Optional[str] = None,
    tags: Optional[List[str]] = None,
    extra: Optional[Dict[str, str]] = None,
    max_chars: int = 800,
    overlap: int = 120,
) -> IngestResult:
    """Ingest raw content (text/markdown) into the processed corpus."""

    metrics = get_metrics()
    start_total = time.perf_counter()

    with time_phase_endpoint(metrics, "ingest_total", "/v1/ingest"):
        with time_phase(metrics, "ingest_normalize"):
            ensure_dirs()
            normalized = normalize_text(content)

        doc_identifier = _sanitize_doc_id(doc_id or source_name)

        with time_phase(metrics, "ingest_chunk"):
            chunked = simple_paragraph_chunk(
                normalized, doc_id=doc_identifier, max_chars=max_chars, overlap=overlap
            )

        with time_phase(metrics, "ingest_persist"):
            raw_path = materialize_document(normalized, source_name=doc_identifier)

            cleaned_tags = [t.strip() for t in (tags or []) if t.strip()]
            extra_meta = {"ingest_source": source_name}
            if extra:
                extra_meta.update(extra)

            document = Document(
                doc_id=doc_identifier,
                source_name=source_name,
                language=language,
                url=url,
                domain=domain,
                freshness=freshness,
                checksum=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                tags=cleaned_tags,
                extra=extra_meta,
            )
            document = upsert_document(document)
            chunk_path = save_chunks(doc_identifier, chunked)

        job_duration_ms = (time.perf_counter() - start_total) * 1000

        append_job_history(
            {
                "job_type": "ingest",
                "status": "succeeded",
                "doc_id": document.doc_id,
                "chunk_count": len(chunked),
                "language": document.language,
                "duration_ms": job_duration_ms,
                "metadata": {
                    "source_name": source_name,
                    "domain": domain,
                },
            }
        )

        log.info(
            "ingested_document",
            doc_id=document.doc_id,
            chunks=len(chunked),
            version=document.version,
            language=document.language,
            domain=document.domain,
        )

        return IngestResult(
            document=document,
            chunk_count=len(chunked),
            raw_path=raw_path,
            chunk_path=chunk_path,
        )


def ingest_file(
    path: Path,
    *,
    doc_id: Optional[str] = None,
    language: str = "auto",
    domain: Optional[str] = None,
    freshness: Optional[str] = None,
    url: Optional[str] = None,
    tags: Optional[List[str]] = None,
    extra: Optional[Dict[str, str]] = None,
    max_chars: int = 800,
    overlap: int = 120,
) -> IngestResult:
    """Ingest a local text/markdown file into the processed corpus."""

    ensure_dirs()
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    content = path.read_text(encoding="utf-8", errors="ignore")
    extra_meta = {"ingest_path": str(path)}
    if extra:
        extra_meta.update(extra)

    return ingest_content(
        content,
        source_name=path.name,
        doc_id=doc_id or path.stem,
        language=language,
        domain=domain,
        freshness=freshness,
        url=url,
        tags=tags,
        extra=extra_meta,
        max_chars=max_chars,
        overlap=overlap,
    )

