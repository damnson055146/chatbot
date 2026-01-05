from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str
    text: str
    start_idx: int
    end_idx: int
    metadata: dict


_BOUNDARY_CHARS = {".", "!", "?", "。", "！", "？", ";", "；", ":", "："}


def _iter_paragraphs(text: str) -> List[Tuple[str, int, int]]:
    paragraphs: List[Tuple[str, int, int]] = []
    lines = text.splitlines(keepends=True)
    pos = 0
    para_start = None
    buffer = ""
    para_index = 0
    for line in lines:
        if not line.strip():
            if buffer:
                paragraphs.append((buffer, para_start or 0, para_index))
                buffer = ""
                para_start = None
                para_index += 1
            pos += len(line)
            continue
        if buffer == "":
            para_start = pos
        buffer += line
        pos += len(line)
    if buffer:
        paragraphs.append((buffer, para_start or 0, para_index))
    return paragraphs


def _trim_span(text: str, start: int, end: int) -> Tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _segment_spans(text: str) -> List[Tuple[int, int, int]]:
    spans: List[Tuple[int, int, int]] = []
    for para_text, para_start, para_index in _iter_paragraphs(text):
        local_start = 0
        for idx, ch in enumerate(para_text):
            if ch in _BOUNDARY_CHARS:
                local_end = idx + 1
                start_idx, end_idx = _trim_span(
                    text, para_start + local_start, para_start + local_end
                )
                if end_idx > start_idx:
                    spans.append((start_idx, end_idx, para_index))
                local_start = local_end
        if local_start < len(para_text):
            start_idx, end_idx = _trim_span(
                text, para_start + local_start, para_start + len(para_text)
            )
            if end_idx > start_idx:
                spans.append((start_idx, end_idx, para_index))
    if not spans and text.strip():
        start_idx, end_idx = _trim_span(text, 0, len(text))
        if end_idx > start_idx:
            spans.append((start_idx, end_idx, 0))
    return spans


def simple_paragraph_chunk(text: str, doc_id: str, max_chars: int = 800, overlap: int = 120) -> List[Chunk]:
    spans = _segment_spans(text)
    if not spans:
        return []

    chunks: List[Chunk] = []
    idx = 0
    while idx < len(spans):
        start_idx, end_idx, para_index = spans[idx]
        para_end = idx
        while para_end < len(spans) and spans[para_end][2] == para_index:
            para_end += 1
        end_idx = max(end_idx, start_idx)
        next_idx = idx + 1
        while next_idx < para_end and spans[next_idx][1] - start_idx <= max_chars:
            end_idx = spans[next_idx][1]
            next_idx += 1
        chunk_text = text[start_idx:end_idx]
        chunk_id = f"{doc_id}-{idx}-{start_idx}"
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=chunk_id,
                text=chunk_text,
                start_idx=start_idx,
                end_idx=end_idx,
                metadata={
                    "doc_id": doc_id,
                    "para": para_index,
                    "start_idx": start_idx,
                    "end_idx": end_idx,
                    "local_start": 0,
                    "local_end": max(0, end_idx - start_idx),
                },
            )
        )
        if next_idx >= para_end:
            idx = para_end
            continue
        if overlap <= 0:
            idx = next_idx
            continue
        overlap_len = 0
        back_idx = next_idx - 1
        while back_idx >= idx and overlap_len < overlap:
            overlap_len += spans[back_idx][1] - spans[back_idx][0]
            back_idx -= 1
        next_start = max(back_idx + 1, idx + 1)
        idx = next_start
    return chunks


def iter_chunks_texts(chunks: Iterable[Chunk]) -> List[str]:
    return [c.text for c in chunks]
