"""Finding the chunks most similar to a question, with pgvector.

The query orders chunks by cosine distance (pgvector's <=> operator, which
the HNSW index on chunks.embedding was built for) and keeps the top k.

It filters on the document *and* joins to documents to check the owner, so
even a caller that skipped the ownership check elsewhere could never read
another user's chunks. Everything goes through SQLAlchemy with bound
parameters; no SQL is built from strings.

Filtering and HNSW: an HNSW index returns the nearest vectors across *all*
documents, and the WHERE clause is applied afterwards. If most of those
nearest vectors belong to other documents, fewer than k rows survive the
filter. pgvector 0.8's iterative scan (hnsw.iterative_scan) keeps walking
the index until k matching rows are found. "relaxed_order" allows results
to come back slightly out of order, so they are re-sorted in Python. For a
single lecture (a few hundred chunks), Postgres often skips the HNSW index
and does an exact search via the document_id index instead; either way the
answer is correct.
"""

from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Chunk, Document


@dataclass(frozen=True)
class RetrievedChunk:
    id: int
    page_start: int
    page_end: int
    text: str
    distance: float  # cosine distance: 0 = same direction, 2 = opposite


def retrieve(
    db: Session, *, document_id: int, user_id: int, query_vector: list[float], top_k: int
) -> list[RetrievedChunk]:
    # SET LOCAL lasts only until the end of the current transaction.
    db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    rows = db.execute(
        select(Chunk.id, Chunk.page_start, Chunk.page_end, Chunk.text, distance)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.document_id == document_id, Document.user_id == user_id)
        .order_by(distance)
        .limit(top_k)
    ).all()
    chunks = [
        RetrievedChunk(r.id, r.page_start, r.page_end, r.text, float(r.distance)) for r in rows
    ]
    return sorted(chunks, key=lambda c: c.distance)
