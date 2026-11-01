"""Answering one question: embed -> retrieve -> prompt -> LLM -> citations -> audit log.

Like the ingestion pipeline, this knows nothing about Flask, so the API and
the evaluation harness run the same code.

Every question is written to the queries table, including failed ones
(with answer = NULL), so there is a complete audit trail of who asked what,
about which document, which chunks were sent to which provider, and how
long it took. Application logs only record IDs and timings, never the
question or answer text.
"""

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.embeddings.base import Embedder
from app.llm.router import LLMRouter
from app.models import Chunk, QueryLog
from app.rag.prompt import REFUSAL, SYSTEM_PROMPT, build_user_prompt, cited_pages, is_refusal
from app.rag.retrieval import RetrievedChunk, retrieve

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 300
# Messages loaded when a chat is reopened.
HISTORY_LIMIT = 100


@dataclass(frozen=True)
class Source:
    chunk_id: int
    page_start: int
    page_end: int
    snippet: str
    cited: bool  # the answer cites a page this chunk covers


@dataclass(frozen=True)
class Answer:
    text: str
    provider: str | None  # None when no LLM was needed (nothing retrieved)
    refused: bool
    sources: list[Source]
    latency_ms: int


def answer_question(
    db: Session,
    *,
    user_id: int,
    document_id: int,
    question: str,
    embedder: Embedder,
    router: LLMRouter,
    requested_provider: str | None,
    top_k: int,
    prefer: str | None = None,
) -> Answer:
    started = time.perf_counter()
    chunks: list[RetrievedChunk] = []
    try:
        chunks = retrieve(
            db,
            document_id=document_id,
            user_id=user_id,
            query_vector=embedder.embed_query(question),
            top_k=top_k,
        )
        if chunks:
            excerpts = [(c.page_start, c.page_end, c.text) for c in chunks]
            routed = router.generate(
                SYSTEM_PROMPT,
                build_user_prompt(question, excerpts),
                requested_provider,
                prefer=prefer,
            )
            text, provider = routed.text, routed.provider
        else:
            text, provider = REFUSAL, None
    except Exception:
        db.rollback()
        _audit(db, user_id, document_id, question, None, None, chunks, started)
        raise

    refused = is_refusal(text)
    sources = build_sources(chunks, text)
    latency_ms = _audit(db, user_id, document_id, question, text, provider, chunks, started)
    logger.info(
        "ask.answered document_id=%s provider=%s refused=%s chunks=%s latency_ms=%s",
        document_id,
        provider,
        refused,
        len(chunks),
        latency_ms,
    )
    return Answer(text, provider, refused, sources, latency_ms)


class _ChunkLike(Protocol):
    @property
    def id(self) -> int: ...
    @property
    def page_start(self) -> int: ...
    @property
    def page_end(self) -> int: ...
    @property
    def text(self) -> str: ...


def build_sources(chunks: Sequence[_ChunkLike], answer: str) -> list[Source]:
    """The chunks shown under an answer, each marked if the answer cites its pages."""
    pages = set() if is_refusal(answer) else cited_pages(answer)
    return [
        Source(
            chunk_id=c.id,
            page_start=c.page_start,
            page_end=c.page_end,
            snippet=_snippet(c.text),
            cited=any(c.page_start <= page <= c.page_end for page in pages),
        )
        for c in chunks
    ]


@dataclass(frozen=True)
class PastAnswer:
    question: str
    answer: Answer
    asked_at: datetime


def chat_history(
    db: Session, *, user_id: int, document_id: int, limit: int = HISTORY_LIMIT
) -> list[PastAnswer]:
    """The latest answered questions about a document, oldest first.

    Rebuilt from the audit log, so a chat survives reloads and devices
    without a second copy of every message. Failed attempts (answer NULL)
    are left out. The sources are looked up again by the chunk IDs the
    audit row recorded, limited to this document's chunks.
    """
    rows = list(
        db.scalars(
            select(QueryLog)
            .where(
                QueryLog.user_id == user_id,
                QueryLog.document_id == document_id,
                QueryLog.answer.is_not(None),
            )
            .order_by(QueryLog.created_at.desc(), QueryLog.id.desc())
            .limit(limit)
        )
    )
    rows.reverse()
    chunk_ids = {chunk_id for row in rows for chunk_id in row.retrieved_chunk_ids}
    chunks = {
        c.id: c
        for c in db.scalars(
            select(Chunk).where(Chunk.document_id == document_id, Chunk.id.in_(chunk_ids))
        )
    }
    history = []
    for row in rows:
        text = row.answer or ""
        found = [chunks[i] for i in row.retrieved_chunk_ids if i in chunks]
        answer = Answer(
            text, row.provider, is_refusal(text), build_sources(found, text), row.latency_ms
        )
        history.append(PastAnswer(row.question, answer, row.created_at))
    return history


def _audit(
    db: Session,
    user_id: int,
    document_id: int,
    question: str,
    answer: str | None,
    provider: str | None,
    chunks: list[RetrievedChunk],
    started: float,
) -> int:
    latency_ms = round((time.perf_counter() - started) * 1000)
    db.add(
        QueryLog(
            user_id=user_id,
            document_id=document_id,
            question=question,
            answer=answer,
            provider=provider,
            retrieved_chunk_ids=[c.id for c in chunks],
            latency_ms=latency_ms,
        )
    )
    db.commit()
    return latency_ms


def _snippet(text: str) -> str:
    if len(text) <= SNIPPET_CHARS:
        return text
    return text[:SNIPPET_CHARS].rsplit(" ", 1)[0] + " ..."
