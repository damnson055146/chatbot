from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class Chunk:
    doc_id: str
    chunk_id: str
    text: str
    start_idx: int
    end_idx: int
    metadata: dict


def simple_paragraph_chunk(text: str, doc_id: str, max_chars: int = 800, overlap: int = 120) -> List[Chunk]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[Chunk] = []
    idx = 0
    for i, para in enumerate(paragraphs):
        start = 0
        while start < len(para):
            end = min(start + max_chars, len(para))
            slice_end = end
            slice_text = para[start:end]
            # add overlap window for continuity
            if end < len(para):
                slice_end = min(end + overlap, len(para))
                slice_text = para[start:slice_end]
            chunk_id = f"{doc_id}-{i}-{start}"
            chunk_start_idx = idx + start
            chunk_end_idx = idx + slice_end
            chunks.append(
                Chunk(
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    text=slice_text,
                    start_idx=chunk_start_idx,
                    end_idx=chunk_end_idx,
                    metadata={
                        "doc_id": doc_id,
                        "para": i,
                        "start_idx": chunk_start_idx,
                        "end_idx": chunk_end_idx,
                        "local_start": start,
                        "local_end": slice_end,
                    },
                )
            )
            start = end
        idx += len(para) + 2  # account for double newline separator
    return chunks


def iter_chunks_texts(chunks: Iterable[Chunk]) -> List[str]:
    return [c.text for c in chunks]

