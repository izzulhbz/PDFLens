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
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.embeddings.base import Embedder
from app.llm.router import LLMRouter
from app.models import QueryLog
from app.rag.prompt import REFUSAL, SYSTEM_PROMPT, build_user_prompt, cited_pages, is_refusal
from app.rag.retrieval import RetrievedChunk, retrieve

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 300


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
                SYSTEM_PROMPT, build_user_prompt(question, excerpts), requested_provider
            )
            text, provider = routed.text, routed.provider
        else:
            text, provider = REFUSAL, None
    except Exception:
        db.rollback()
        _audit(db, user_id, document_id, question, None, None, chunks, started)
        raise

    refused = is_refusal(text)
    pages = set() if refused else cited_pages(text)
    sources = [
        Source(
            chunk_id=c.id,
            page_start=c.page_start,
            page_end=c.page_end,
            snippet=_snippet(c.text),
            cited=any(c.page_start <= page <= c.page_end for page in pages),
        )
        for c in chunks
    ]
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
