"""Chats in the History panel: titles, reloading a chat's messages, and deleting a chat."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.base import LLMError
from app.models import Chunk, Document, DocumentStatus, QueryLog
from tests.conftest import api_client, make_integration_app, register, upload
from tests.fakes import ScriptedLLM
from tests.pdf_factory import make_pdf

LECTURE = make_pdf(
    [
        "Embeddings turn text into vectors of numbers. They capture meaning.",
        "HNSW builds a layered graph so nearest neighbour search is fast.",
    ]
)


def new_lecture(client) -> int:
    document_id: int = upload(client, LECTURE).get_json()["document"]["id"]
    return document_id


def ask(client, document_id, question):
    return client.post("/api/ask", json={"document_id": document_id, "question": question})


def messages(client, document_id):
    return client.get(f"/api/documents/{document_id}/messages")


# --- Titles -------------------------------------------------------------------------------


def test_title_is_empty_until_the_summary_names_the_document(client):
    register(client)
    document_id = new_lecture(client)

    assert client.get(f"/api/documents/{document_id}").get_json()["document"]["title"] is None

    client.post(f"/api/documents/{document_id}/summary", json={})
    listed = client.get("/api/documents").get_json()["documents"][0]

    assert listed["title"].startswith("Embeddings turn text into vectors")


# --- Chat history ------------------------------------------------------------------------


def test_chat_history_returns_answered_questions_oldest_first_with_sources(client):
    register(client)
    document_id = new_lecture(client)
    first = ask(client, document_id, "What does HNSW build?").get_json()
    ask(client, document_id, "What do embeddings turn text into?")

    response = messages(client, document_id)

    assert response.status_code == 200
    history = response.get_json()["messages"]
    assert [m["question"] for m in history] == [
        "What does HNSW build?",
        "What do embeddings turn text into?",
    ]
    # The same shape as a live answer, so the UI renders both the same way.
    assert history[0]["answer"] == first["answer"]
    assert history[0]["sources"] == first["sources"]
    assert history[0]["refused"] is False
    assert "asked_at" in history[0]


def test_failed_attempts_are_audited_but_not_shown_in_the_chat(
    db_engine, test_database_url, upload_dir
):
    down = ScriptedLLM("ollama", error=LLMError("unreachable", can_fall_back=False))
    app = make_integration_app(test_database_url, upload_dir, ollama_llm=down)
    client = api_client(app)
    register(client)
    document_id = new_lecture(client)

    assert ask(client, document_id, "What does HNSW build?").status_code == 503

    assert messages(client, document_id).get_json()["messages"] == []
    with Session(db_engine) as db:
        assert db.scalars(select(QueryLog)).one().answer is None


def test_chats_are_separate_per_document(client):
    register(client)
    first, second = new_lecture(client), new_lecture(client)
    ask(client, first, "What does HNSW build?")

    assert len(messages(client, first).get_json()["messages"]) == 1
    assert messages(client, second).get_json()["messages"] == []


def test_another_users_chat_is_a_404(app, client):
    register(client)
    document_id = new_lecture(client)
    ask(client, document_id, "What does HNSW build?")
    mallory = api_client(app)
    register(mallory, "mallory@example.com")

    response = messages(mallory, document_id)

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "document_not_found"


def test_chat_history_requires_login(app, client):
    register(client)
    document_id = new_lecture(client)

    assert messages(api_client(app), document_id).status_code == 401


# --- Deleting a chat ---------------------------------------------------------------------


def test_deleting_removes_the_document_its_chunks_and_its_file(client, db_engine, upload_dir):
    register(client)
    document_id = new_lecture(client)
    assert list(upload_dir.iterdir())

    response = client.delete(f"/api/documents/{document_id}")

    assert response.status_code == 204
    assert client.get(f"/api/documents/{document_id}").status_code == 404
    assert client.get("/api/documents").get_json()["documents"] == []
    assert list(upload_dir.iterdir()) == []
    with Session(db_engine) as db:
        assert db.scalars(select(Chunk)).all() == []


def test_deleting_keeps_the_audit_log_but_detaches_it(client, db_engine):
    register(client)
    document_id = new_lecture(client)
    ask(client, document_id, "What does HNSW build?")

    client.delete(f"/api/documents/{document_id}")

    with Session(db_engine) as db:
        logged = db.scalars(select(QueryLog)).one()
        assert logged.question == "What does HNSW build?"
        assert logged.document_id is None


def test_cannot_delete_another_users_document(app, client, db_engine, upload_dir):
    register(client)
    document_id = new_lecture(client)
    mallory = api_client(app)
    register(mallory, "mallory@example.com")

    response = mallory.delete(f"/api/documents/{document_id}")

    assert response.status_code == 404
    assert client.get(f"/api/documents/{document_id}").status_code == 200
    assert list(upload_dir.iterdir())


def test_document_still_processing_cannot_be_deleted(client, db_engine):
    register(client)
    document_id = new_lecture(client)
    with Session(db_engine) as db:
        db.get_one(Document, document_id).status = DocumentStatus.PROCESSING
        db.commit()

    response = client.delete(f"/api/documents/{document_id}")

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "document_processing"


def test_deleting_needs_the_csrf_header(app, client):
    register(client)
    document_id = new_lecture(client)
    client.environ_base.pop("HTTP_X_PDFLENS_CSRF")

    assert client.delete(f"/api/documents/{document_id}").status_code == 403
    assert client.get(f"/api/documents/{document_id}").status_code == 200
