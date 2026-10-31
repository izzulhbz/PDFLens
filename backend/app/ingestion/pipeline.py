"""The ingestion pipeline: PDF file -> pages -> clean text -> chunks -> vectors -> database.

This module knows nothing about Flask or threads, so the API worker, the
tests and the evaluation harness all run exactly the same code.
"""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.embeddings.base import Embedder
from app.ingestion.chunking import chunk_pages
from app.ingestion.cleaning import clean_pages
from app.ingestion.pdf import extract_pages
from app.models import Chunk, Document, DocumentStatus


class IngestionError(Exception):
    """The document can't be ingested. The message is safe to show the user."""


@dataclass(frozen=True)
class IngestionResult:
    page_count: int
    chunk_count: int


def ingest_document(
    db: Session, document: Document, pdf_path: Path, embedder: Embedder
) -> IngestionResult:
    """Chunk and embed one document, store its chunks, and mark it ready.

    Commits on success. On failure it raises and leaves the transaction for
    the caller to roll back, so a half-ingested document never has chunks.
    """
    pages = clean_pages(extract_pages(pdf_path))
    chunks = chunk_pages(pages)
    if not chunks:
        raise IngestionError(
            "No text could be found in this PDF. Scanned documents (photos of pages) "
            "aren't supported."
        )

    vectors = embedder.embed_documents([chunk.text for chunk in chunks])

    db.add_all(
        Chunk(
            document_id=document.id,
            chunk_index=chunk.index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            text=chunk.text,
            embedding=vector,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    )
    document.status = DocumentStatus.READY
    document.error_message = None
    db.commit()
    return IngestionResult(page_count=len(pages), chunk_count=len(chunks))
