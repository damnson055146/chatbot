from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

from fastapi import HTTPException

from src.utils import siliconflow

@dataclass(frozen=True)
class ExtractedText:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def _extract_image_text(content: bytes, *, filename: str, mime_type: str) -> ExtractedText:
    try:
        result = siliconflow.ocr_image(
            content,
            filename=filename,
            mime_type=mime_type,
        )
    except siliconflow.SiliconFlowConfigError as exc:
        raise HTTPException(status_code=400, detail="OCR is not available (SILICONFLOW_API_KEY missing)") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="OCR failed to extract text from image") from exc

    text = str(result.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Image OCR produced no readable text")

    return ExtractedText(
        text=text,
        metadata={
            "ocr_engine": "qwen_vl",
            "ocr_model": result.get("model"),
        },
    )


def _extract_audio_text(content: bytes, *, mime_type: str, filename: str) -> ExtractedText:
    stt_language = os.getenv("SILICONFLOW_STT_LANGUAGE")
    try:
        result = siliconflow.transcribe_audio(
            content,
            filename=filename,
            mime_type=mime_type,
            language=stt_language,
        )
    except siliconflow.SiliconFlowConfigError as exc:
        raise HTTPException(status_code=400, detail="STT is not available (SILICONFLOW_API_KEY missing)") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unable to transcribe audio") from exc

    text = str(result.get("text") or "").strip()
    segments = result.get("segments") or result.get("chunks") or []
    if not isinstance(segments, list):
        segments = []

    if not text:
        raise HTTPException(status_code=400, detail="Audio transcription produced no readable text")

    if not segments:
        segments = [{"start": None, "end": None, "text": text}]

    return ExtractedText(
        text=text,
        metadata={
            "stt_engine": "siliconflow",
            "stt_model": result.get("model"),
            "stt_language": stt_language,
            "stt_segments": segments,
        },
    )


def extract_text_from_bytes(*, content: bytes, mime_type: str, filename: str) -> ExtractedText:
    """Extract plain text from uploaded bytes.

    Supports text/*, JSON, PDF extraction, image OCR (Qwen/Qwen3-VL-32B-Instruct), and audio STT.
    """

    kind = (mime_type or "application/octet-stream").lower().strip()

    if kind.startswith("text/") or kind in {"application/json"}:
        try:
            text = content.decode("utf-8", errors="ignore").strip()
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=400, detail=f"Unable to decode file: {filename}") from exc
        if not text:
            raise HTTPException(status_code=400, detail="Uploaded text file contains no readable content")
        return ExtractedText(text=text, metadata={"source_type": "text"})

    if kind == "application/pdf":
        try:
            from pypdf import PdfReader  # lazy import to keep startup light
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=400, detail="PDF extraction is not available (pypdf missing)") from exc

        try:
            reader = PdfReader(io.BytesIO(content))
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            text = "\n\n".join([p.strip() for p in pages if p and p.strip()]).strip()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Unable to extract text from PDF") from exc

        if not text:
            raise HTTPException(status_code=400, detail="PDF contains no extractable text (OCR required)")
        return ExtractedText(text=text, metadata={"source_type": "pdf", "pdf_pages": len(reader.pages)})

    if kind.startswith("image/"):
        return _extract_image_text(content, filename=filename, mime_type=kind)

    if kind.startswith("audio/"):
        return _extract_audio_text(content, mime_type=kind, filename=filename)

    raise HTTPException(status_code=400, detail=f"Unsupported ingestion type: {mime_type}")


