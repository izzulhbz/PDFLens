"""Database constraints and pgvector search, tested against real Postgres.

The application validates input too, but these constraints are the last
line of defence: they hold even if a bug in the app tries to write bad data.
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.models import EMBEDDING_DIM, Chunk, Document, DocumentStatus, QueryLog, User


def unit_vector(position: int) -> list[float]:
    """A vector pointing along one axis, for easy-to-reason-about distances."""
    vector = [0.0] * EMBEDDING_DIM
    vector[position] = 1.0
    return vector


def add_user_with_document(session: Session, email: str = "alice@example.com") -> Document:
    user = User(email=email, password_hash="not-a-real-hash")
    session.add(user)
    session.flush()
    document = Document(
        user_id=user.id,
        original_filename="lecture.pdf",
        stored_filename=f"{user.id}-stored.pdf",
        page_count=3,
    )
    session.add(document)
    session.flush()
    return document


def test_new_document_defaults_to_processing(db_engine):
    with Session(db_engine) as session:
        document = add_user_with_document(session)
        session.commit()
        session.refresh(document)

    assert document.status == DocumentStatus.PROCESSING


def test_email_must_be_lowercase(db_engine):
    with Session(db_engine) as session:
        session.add(User(email="Alice@Example.com", password_hash="x"))
        with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
            session.flush()


def test_email_must_be_unique(db_engine):
    with Session(db_engine) as session:
        session.add(User(email="alice@example.com", password_hash="x"))
        session.flush()
        session.add(User(email="alice@example.com", password_hash="y"))
        with pytest.raises(IntegrityError, match="uq_users_email"):
            session.flush()


def test_document_status_must_be_known(db_engine):
    with Session(db_engine) as session:
        document = add_user_with_document(session)
        document.status = "deleted"
        with pytest.raises(IntegrityError, match="ck_documents_status_valid"):
            session.flush()


def test_chunk_page_range_must_be_valid(db_engine):
    with Session(db_engine) as session:
        document = add_user_with_document(session)
        session.add(
            Chunk(
                document_id=document.id,
                chunk_index=0,
                page_start=3,
                page_end=2,
                text="x",
                embedding=unit_vector(0),
            )
        )
        with pytest.raises(IntegrityError, match="ck_chunks_page_range_valid"):
            session.flush()


def test_database_rejects_embedding_of_wrong_dimension(db_engine):
    # Raw SQL on purpose, to show Postgres itself enforces vector(768), not
    # just the Python library. (The vector is still a bound parameter.)
    with Session(db_engine) as session:
        document = add_user_with_document(session)
        with pytest.raises(DataError, match="expected 768 dimensions"):
            session.execute(
                text(
                    "INSERT INTO chunks (document_id, chunk_index, page_start, page_end, text,"
                    " embedding) VALUES (:doc, 0, 1, 1, 'x', CAST(:embedding AS vector))"
                ),
                {"doc": document.id, "embedding": "[1, 2, 3]"},
            )


def test_deleting_a_user_deletes_their_documents_and_chunks(db_engine):
    with Session(db_engine) as session:
        document = add_user_with_document(session)
        session.add(
            Chunk(
                document_id=document.id,
                chunk_index=0,
                page_start=1,
                page_end=1,
                text="x",
                embedding=unit_vector(0),
            )
        )
        session.commit()

        session.execute(text("DELETE FROM users"))
        session.commit()

        assert session.scalar(select(Document)) is None
        assert session.scalar(select(Chunk)) is None


def test_deleting_a_document_keeps_its_audit_records(db_engine):
    with Session(db_engine) as session:
        document = add_user_with_document(session)
        session.add(
            QueryLog(
                user_id=document.user_id,
                document_id=document.id,
                question="What is HNSW?",
                answer="An index.",
                provider="ollama",
                retrieved_chunk_ids=[1, 2],
                latency_ms=120,
            )
        )
        session.commit()

        session.delete(document)
        session.commit()

        query_log = session.scalars(select(QueryLog)).one()
        assert query_log.document_id is None
        assert query_log.retrieved_chunk_ids == [1, 2]


def test_cosine_distance_returns_nearest_chunks_first(db_engine):
    with Session(db_engine) as session:
        document = add_user_with_document(session)
        for index, axis in enumerate([0, 1, 2]):
            session.add(
                Chunk(
                    document_id=document.id,
                    chunk_index=index,
                    page_start=index + 1,
                    page_end=index + 1,
                    text=f"chunk {index}",
                    embedding=unit_vector(axis),
                )
            )
        session.commit()

        # A query vector mostly along axis 1, a little along axis 0.
        question = [0.0] * EMBEDDING_DIM
        question[0], question[1] = 0.3, 0.9

        nearest = session.scalars(
            select(Chunk.chunk_index).order_by(Chunk.embedding.cosine_distance(question)).limit(2)
        ).all()

    assert nearest == [1, 0]
