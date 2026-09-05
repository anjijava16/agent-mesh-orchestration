"""Chunking.

Recursive splitting on structural boundaries, then a token-aware size check.
Overlap is kept because retrieval quality at the chunk boundary is where most
RAG systems quietly lose answers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings
from app.ingestion.parsers import ParsedPage

SEPARATORS = ["\n## ", "\n# ", "\n\n", "\n", ". ", " "]


@dataclass
class Chunk:
    index: int
    page: int
    text: str
    token_estimate: int


def _split(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text] if text.strip() else []

    for sep in SEPARATORS:
        if sep in text:
            parts = text.split(sep)
            chunks: list[str] = []
            current = ""
            for part in parts:
                candidate = f"{current}{sep}{part}" if current else part
                if len(candidate) > size and current:
                    chunks.append(current)
                    tail = current[-overlap:] if overlap else ""
                    current = f"{tail}{sep}{part}" if tail else part
                else:
                    current = candidate
            if current.strip():
                chunks.append(current)
            if len(chunks) > 1:
                return [c for c in chunks if c.strip()]

    # No usable separator - hard window.
    step = max(1, size - overlap)
    return [text[i:i + size] for i in range(0, len(text), step) if text[i:i + size].strip()]


def chunk_pages(pages: list[ParsedPage], *, size: int | None = None, overlap: int | None = None) -> list[Chunk]:
    size = size or settings.ingestion.chunk_size
    overlap = overlap or settings.ingestion.chunk_overlap

    out: list[Chunk] = []
    index = 0
    for page in pages:
        cleaned = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]{2,}", " ", page.text)).strip()
        for piece in _split(cleaned, size, overlap):
            out.append(Chunk(index=index, page=page.page, text=piece.strip(), token_estimate=len(piece) // 4))
            index += 1
    return out
