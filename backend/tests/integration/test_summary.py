"""Summary endpoints against real Postgres, with the fake embedder and LLMs."""

import json

import pytest
from sqlalchemy.orm import Session

from app.llm.base import LLMError
from app.models import Document, DocumentStatus
from tests.conftest import api_client, make_integration_app, register, upload
from tests.fakes import ScriptedLLM
from tests.pdf_factory import make_pdf

LECTURE = make_pdf(
    [
        "Embeddings turn text into vectors of numbers. They capture meaning.",
        "HNSW builds a layered graph so nearest neighbour search is fast.",
    ]
)
GOOD_SUMMARY = {
    "title": "Vector search",
    "overview": "How embeddings and HNSW work.",
    "topics": [{"name": "HNSW", "summary": "A layered graph.", "pages": [2]}],
    "learning_outcomes": ["Explain HNSW"],
    "key_terms": [],
}


@pytest.fixture
def lecture_id(client) -> int:
    register(client)
    document_id: int = upload(client, LECTURE).get_json()["document"]["id"]
    return document_id


def summarise(client, document_id, **body):
    return client.post(f"/api/documents/{document_id}/summary", json=body)


def test_no_summary_until_one_is_requested(client, lecture_id):
    response = client.get(f"/api/documents/{lecture_id}/summary")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "summary_not_found"


def test_summary_is_generated_saved_and_then_served_from_the_database(
    client, lecture_id, db_engine
):
    created = summarise(client, lecture_id)

    assert created.status_code == 200
    body = created.get_json()
    assert body["provider"] == "mock"
    assert body["summary"]["overview"].startswith("Embeddings turn text into vectors")
    assert body["summary"]["topics"][0]["pages"] == [1, 2]

    with Session(db_engine) as db:
        stored = db.get_one(Document, lecture_id)
        assert stored.summary == body["summary"]
        assert stored.summary_provider == "mock"

    assert client.get(f"/api/documents/{lecture_id}/summary").get_json() == body


def test_summary_requests_json_and_walls_off_the_pdf_text(db_engine, test_database_url, upload_dir):
    llm = ScriptedLLM("ollama", json.dumps(GOOD_SUMMARY))
    app = make_integration_app(test_database_url, upload_dir, ollama_llm=llm)
    client = api_client(app)
    register(client)
    document_id = upload(client, LECTURE).get_json()["document"]["id"]

    summarise(client, document_id, provider="ollama")

    [(system, user)] = llm.calls
    assert llm.schemas[0] is not None and "topics" in llm.schemas[0]["properties"]
    assert "untrusted" in system
    assert user.startswith("<document_excerpts>")


def test_unusable_model_output_is_a_502(db_engine, test_database_url, upload_dir):
    app = make_integration_app(
        test_database_url, upload_dir, ollama_llm=ScriptedLLM("ollama", "I am not JSON")
    )
    client = api_client(app)
    register(client)
    document_id = upload(client, LECTURE).get_json()["document"]["id"]

    response = summarise(client, document_id)

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "summary_invalid"
    assert client.get(f"/api/documents/{document_id}/summary").status_code == 404


def test_provider_failure_is_a_503(db_engine, test_database_url, upload_dir):
    down = ScriptedLLM("ollama", error=LLMError("unreachable", can_fall_back=False))
    app = make_integration_app(test_database_url, upload_dir, ollama_llm=down)
    client = api_client(app)
    register(client)
    document_id = upload(client, LECTURE).get_json()["document"]["id"]

    assert summarise(client, document_id).status_code == 503


def test_invalid_provider_is_a_400(client, lecture_id):
    response = summarise(client, lecture_id, provider="gpt-4")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_provider"


def test_another_users_summary_is_a_404(app, client, lecture_id):
    summarise(client, lecture_id)
    mallory = api_client(app)
    register(mallory, "mallory@example.com")

    assert mallory.get(f"/api/documents/{lecture_id}/summary").status_code == 404
    assert summarise(mallory, lecture_id).status_code == 404


def test_document_still_processing_is_409(client, lecture_id, db_engine):
    with Session(db_engine) as db:
        db.get_one(Document, lecture_id).status = DocumentStatus.PROCESSING
        db.commit()

    assert summarise(client, lecture_id).status_code == 409


def test_summaries_are_rate_limited_per_user(db_engine, test_database_url, upload_dir):
    app = make_integration_app(test_database_url, upload_dir, rate_limit_summary="1 per hour")
    client = api_client(app)
    register(client)
    document_id = upload(client, LECTURE).get_json()["document"]["id"]

    assert summarise(client, document_id).status_code == 200
    assert summarise(client, document_id).status_code == 429
