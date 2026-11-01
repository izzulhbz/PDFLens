"""Nothing private reaches the logs, even when the database rejects a write.

Postgres puts the rejected row into its error message ("Failing row contains
(..., <document text>, ...)"), and SQLAlchemy adds the statement's parameter
values. Both would land in the logs with an ordinary log.exception().
"""

import logging

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.logging_config import log_unexpected_error
from app.models import Chunk, Document, User

SECRET_TEXT = "Confidential lecture text that must never be logged"
logger = logging.getLogger("test_log_safety")


def test_sql_parameter_values_are_hidden_from_database_errors(app):
    db = sessionmaker(app.extensions["db_engine"])()
    db.add(User(email="NOT-LOWERCASE@example.com", password_hash=SECRET_TEXT))

    with pytest.raises(IntegrityError) as raised:
        db.flush()  # breaks ck_users_email_lowercase
    db.close()

    assert "[SQL parameters hidden due to hide_parameters=True]" in str(raised.value)


def test_a_failed_chunk_insert_is_logged_without_the_document_text(app, caplog):
    # What the ingestion worker logs if saving a chunk fails.
    db = sessionmaker(app.extensions["db_engine"])()
    user = User(email="alice@example.com", password_hash="hash")
    db.add(user)
    db.flush()
    document = Document(user_id=user.id, original_filename="x.pdf", stored_filename="a" * 32)
    db.add(document)
    db.flush()
    bad_range = Chunk(
        document_id=document.id,
        chunk_index=0,
        page_start=5,
        page_end=2,  # breaks ck_chunks_page_range_valid
        text=SECRET_TEXT,
        embedding=[0.0] * 768,
    )
    db.add(bad_range)

    with caplog.at_level(logging.ERROR):
        try:
            db.flush()
        except IntegrityError:
            log_unexpected_error(logger, "ingestion.failed document_id=%s", document.id)
    db.close()

    assert "IntegrityError sqlstate=23514 constraint=ck_chunks_page_range_valid" in caplog.text
    assert "in do_execute" in caplog.text  # the traceback is still there
    assert SECRET_TEXT not in caplog.text


def test_an_unexpected_database_error_in_a_request_is_logged_safely(app, client, caplog):
    @app.get("/api/test-only-boom")
    def boom():
        db = sessionmaker(app.extensions["db_engine"])()
        db.add(User(email="NOT-LOWERCASE@example.com", password_hash=SECRET_TEXT))
        db.flush()
        return ""

    with caplog.at_level(logging.ERROR):
        response = client.get("/api/test-only-boom")

    assert response.status_code == 500
    assert SECRET_TEXT not in response.get_data(as_text=True)
    assert "Unhandled exception: IntegrityError" in caplog.text
    assert SECRET_TEXT not in caplog.text


def test_other_unexpected_errors_keep_their_full_message(caplog):
    with caplog.at_level(logging.ERROR):
        try:
            raise ValueError("ordinary bug")
        except ValueError:
            log_unexpected_error(logger, "failed")

    assert "ValueError: ordinary bug" in caplog.text
