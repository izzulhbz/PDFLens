"""The ingestion worker: background processing, failures and restart recovery."""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.embeddings.base import EmbeddingError
from app.ingestion.worker import GENERIC_FAILURE, INTERRUPTED
from app.models import Chunk, Document, DocumentStatus, User
from tests.conftest import api_client, make_integration_app, register, upload
from tests.pdf_factory import make_pdf, words

LECTURE = make_pdf(["Embeddings map text to vectors. " + words(400)])


class FailingEmbedder:
    dimension = 768

    def __init__(self, error: Exception) -> None:
        self.error = error

    def embed_documents(self, texts):
        raise self.error

    def embed_query(self, text):
        raise self.error


def chunk_count(db_engine) -> int:
    with Session(db_engine) as db:
        return db.scalar(select(func.count()).select_from(Chunk)) or 0


def test_background_ingestion_finishes_after_the_upload_returns(
    db_engine, test_database_url, upload_dir
):
    app = make_integration_app(test_database_url, upload_dir, inline=False)
    client = api_client(app)
    register(client)

    response = upload(client, LECTURE)
    document_id = response.get_json()["document"]["id"]
    app.extensions["ingestion"].shutdown()  # wait for the background job

    assert response.status_code == 202
    status = client.get(f"/api/documents/{document_id}").get_json()["document"]["status"]
    assert status == "ready"
    assert chunk_count(db_engine) > 0


def test_pdf_without_text_fails_with_a_helpful_message(client, db_engine):
    register(client)

    document = upload(client, make_pdf(["", ""])).get_json()["document"]

    assert document["status"] == "failed"
    assert "Scanned documents" in document["error_message"]
    assert chunk_count(db_engine) == 0


def test_embedding_service_failure_is_reported_and_nothing_is_stored(
    db_engine, test_database_url, upload_dir
):
    error = EmbeddingError("connection refused", user_message="Ollama is down, try later.")
    app = make_integration_app(test_database_url, upload_dir, embedder=FailingEmbedder(error))
    client = api_client(app)
    register(client)

    document = upload(client, LECTURE).get_json()["document"]

    assert document["status"] == "failed"
    assert document["error_message"] == "Ollama is down, try later."
    assert chunk_count(db_engine) == 0


def test_unexpected_errors_are_logged_but_the_user_sees_a_generic_message(
    db_engine, test_database_url, upload_dir, caplog
):
    error = RuntimeError("internal detail: /srv/secret/path")
    app = make_integration_app(test_database_url, upload_dir, embedder=FailingEmbedder(error))
    client = api_client(app)
    register(client)

    with caplog.at_level(logging.ERROR):
        document = upload(client, LECTURE).get_json()["document"]

    assert document["error_message"] == GENERIC_FAILURE
    assert "internal detail" in caplog.text  # full traceback in the server log


def test_ingestion_logs_never_contain_document_text(client, caplog):
    register(client)

    with caplog.at_level(logging.DEBUG):
        upload(client, make_pdf(["A confidential sentence about thermodynamics."]))

    assert "ingestion.ready" in caplog.text
    assert "thermodynamics" not in caplog.text


def test_recover_command_fails_documents_interrupted_by_a_restart(app, db_engine):
    with Session(db_engine) as db:
        user = User(email="alice@example.com", password_hash="x")
        db.add(user)
        db.flush()
        db.add(
            Document(
                user_id=user.id,
                original_filename="stuck.pdf",
                stored_filename="stuck.pdf",
                status=DocumentStatus.PROCESSING,
            )
        )
        db.commit()

    result = app.test_cli_runner().invoke(args=["recover-ingestion"])

    assert "Marked 1 interrupted document(s) as failed." in result.output
    with Session(db_engine) as db:
        document = db.scalars(select(Document)).one()
    assert (document.status, document.error_message) == ("failed", INTERRUPTED)
