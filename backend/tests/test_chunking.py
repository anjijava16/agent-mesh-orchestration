from __future__ import annotations

from app.ingestion.chunking import chunk_pages
from app.ingestion.parsers import ParsedPage


def test_chunks_carry_their_page_number():
    pages = [ParsedPage(1, "alpha " * 400), ParsedPage(2, "beta " * 400)]
    chunks = chunk_pages(pages, size=500, overlap=50)

    assert {c.page for c in chunks} == {1, 2}
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(c.text.strip() for c in chunks)


def test_short_page_stays_one_chunk():
    chunks = chunk_pages([ParsedPage(1, "a short paragraph")], size=1000, overlap=100)
    assert len(chunks) == 1


def test_empty_pages_produce_nothing():
    assert chunk_pages([ParsedPage(1, "   \n\n  ")]) == []
