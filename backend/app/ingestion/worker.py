"""Runs ingestion in the background, so uploads return immediately.

The upload endpoint saves the file, creates the document with status
"processing" and hands its ID to this worker. A background thread does the
slow part (parsing and embedding, seconds to minutes) and sets the status to
"ready" or "failed". The frontend polls the document's status.

There is one worker thread. PyMuPDF can only be used by one thread at a
time anyway, and Ollama on a CPU embeds one batch at a time, so more threads
wouldn't make ingestion faster.

Jobs are only held in memory: if the server restarts mid-job, that job is
lost. `flask recover-ingestion` (run by entrypoint.sh before the server
starts) marks such documents as failed, so they don't stay "processing"
forever. A persistent job queue would let them resume instead.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import click
from flask import Flask
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app.embeddings.base import Embedder, EmbeddingError
from app.ingestion.pipeline import IngestionError, ingest_document
from app.logging_config import log_unexpected_error
from app.models import Document, DocumentStatus
from app.storage import UploadStore

logger = logging.getLogger(__name__)

GENERIC_FAILURE = "Something went wrong while processing this PDF."
INTERRUPTED = "Processing was interrupted by a server restart. Please upload the file again."


class IngestionWorker:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        embedder: Embedder,
        store: UploadStore,
        *,
        inline: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._store = store
        # inline=True runs each job immediately, inside the request. Tests use
        # it so they can check the result right after uploading.
        self._executor = (
            None if inline else ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingestion")
        )

    def submit(self, document_id: int) -> None:
        if self._executor is None:
            self.run(document_id)
        else:
            self._executor.submit(self.run, document_id)

    def shutdown(self) -> None:
        """Wait for queued jobs to finish (used by tests)."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)

    def run(self, document_id: int) -> None:
        """Ingest one document. Never raises: every failure is recorded on the document."""
        started = time.perf_counter()
        # Its own session, separate from any request's: this may run on
        # another thread, long after the request that queued it has ended.
        with self._session_factory() as db:
            document = db.get(Document, document_id)
            if document is None or document.status != DocumentStatus.PROCESSING:
                return
            try:
                pdf_path = self._store.path_for(document.stored_filename)
                result = ingest_document(db, document, pdf_path, self._embedder)
            except Exception as exc:
                db.rollback()
                self._record_failure(db, document_id, exc)
                return

        logger.info(
            "ingestion.ready document_id=%s pages=%s chunks=%s duration_ms=%.0f",
            document_id,
            result.page_count,
            result.chunk_count,
            (time.perf_counter() - started) * 1000,
        )

    def _record_failure(self, db: Session, document_id: int, exc: Exception) -> None:
        if isinstance(exc, IngestionError):
            message = str(exc)
            logger.warning("ingestion.failed document_id=%s reason=%s", document_id, message)
        elif isinstance(exc, EmbeddingError):
            message = exc.user_message
            logger.warning("ingestion.failed document_id=%s embedding_error=%s", document_id, exc)
        else:
            # Unexpected: log the full traceback for us, show a generic message to the user.
            message = GENERIC_FAILURE
            log_unexpected_error(
                logger, "ingestion.failed document_id=%s unexpected error", document_id
            )

        db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=DocumentStatus.FAILED, error_message=message)
        )
        db.commit()


def fail_interrupted_documents(session_factory: sessionmaker[Session]) -> int:
    """Mark documents left in "processing" by a previous run as failed."""
    with session_factory() as db:
        result = db.execute(
            update(Document)
            .where(Document.status == DocumentStatus.PROCESSING)
            .values(status=DocumentStatus.FAILED, error_message=INTERRUPTED)
        )
        db.commit()
        return int(getattr(result, "rowcount", 0))


def register_cli(app: Flask) -> None:
    @app.cli.command("recover-ingestion")
    def recover_ingestion() -> None:
        """Mark documents interrupted by a restart as failed."""
        count = fail_interrupted_documents(app.extensions["db_sessionmaker"])
        click.echo(f"Marked {count} interrupted document(s) as failed.")
