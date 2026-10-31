"""Upload -> ingest -> stored chunks, plus validation and ownership (IDOR) checks."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.documents import MAX_UPLOAD_BYTES
from app.models import EMBEDDING_DIM, Chunk, Document
from tests.conftest import api_client, make_integration_app, register, upload
from tests.pdf_factory import make_pdf, words

LECTURE = make_pdf(
    [
        "Vector databases store embeddings. " + words(250, "intro"),
        "HNSW builds a layered graph for search. " + words(250, "hnsw"),
        "Chunk overlap keeps facts together. " + words(250, "overlap"),
    ],
    header="CS4242 Week 7: Retrieval",
    page_numbers=True,
)


def stored_files(upload_dir):
    return sorted(p.name for p in upload_dir.iterdir()) if upload_dir.exists() else []


# --- The happy path -------------------------------------------------------------------------


def test_upload_ingests_the_pdf_into_chunks(client, db_engine, upload_dir):
    register(client)

    response = upload(client, LECTURE, "Week 7.pdf")

    assert response.status_code == 202
    document = response.get_json()["document"]
    assert document["filename"] == "Week 7.pdf"
    assert document["page_count"] == 3
    # Ingestion runs inline in tests, so it's already finished.
    assert document["status"] == "ready"

    with Session(db_engine) as db:
        chunks = db.scalars(select(Chunk).order_by(Chunk.chunk_index)).all()
    assert len(chunks) >= 2
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 3
    assert all(len(c.embedding) == EMBEDDING_DIM for c in chunks)
    # The repeated header and the page-number footer were cleaned away.
    assert not any("CS4242" in c.text or "Page 2 of 3" in c.text for c in chunks)


def test_file_is_stored_under_a_random_name(client, upload_dir):
    register(client)

    upload(client, LECTURE, "../../../etc/sneaky.pdf")

    [name] = stored_files(upload_dir)
    assert name != "sneaky.pdf" and len(name) == 36
    assert (upload_dir / name).read_bytes() == LECTURE
    assert client.get("/api/documents").get_json()["documents"][0]["filename"] == "sneaky.pdf"


def test_document_list_is_newest_first(client):
    register(client)
    upload(client, LECTURE, "first.pdf")
    upload(client, LECTURE, "second.pdf")

    names = [d["filename"] for d in client.get("/api/documents").get_json()["documents"]]

    assert names == ["second.pdf", "first.pdf"]


# --- Authorisation ---------------------------------------------------------------------


def test_upload_requires_login(client, upload_dir):
    response = upload(client, LECTURE)

    assert response.status_code == 401
    assert stored_files(upload_dir) == []


def test_users_only_see_their_own_documents(app, client):
    register(client, "alice@example.com")
    upload(client, LECTURE, "alice.pdf")
    bob = api_client(app)
    register(bob, "bob@example.com")
    upload(bob, LECTURE, "bob.pdf")

    alice_sees = [d["filename"] for d in client.get("/api/documents").get_json()["documents"]]

    assert alice_sees == ["alice.pdf"]


def test_another_users_document_looks_exactly_like_a_missing_one(app, client):
    register(client, "alice@example.com")
    alice_doc = upload(client, LECTURE).get_json()["document"]["id"]
    bob = api_client(app)
    register(bob, "bob@example.com")

    someone_elses = bob.get(f"/api/documents/{alice_doc}")
    nonexistent = bob.get("/api/documents/999999")

    assert someone_elses.status_code == nonexistent.status_code == 404
    assert someone_elses.get_json() == nonexistent.get_json()
    assert client.get(f"/api/documents/{alice_doc}").status_code == 200


# --- Validation ---------------------------------------------------------------------------


def test_text_file_renamed_to_pdf_is_rejected(client, upload_dir):
    register(client)

    response = upload(client, b"just text, honest", "notes.pdf")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_pdf"
    assert stored_files(upload_dir) == []


def test_real_pdf_with_wrong_extension_is_rejected(client):
    register(client)

    response = upload(client, LECTURE, "lecture.docx")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_file_type"


def test_missing_file_field_is_rejected(client):
    register(client)

    response = client.post("/api/documents", data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "file_missing"


def test_password_protected_pdf_is_rejected(client):
    register(client)

    response = upload(client, make_pdf(["secret"], password="a-long-password"))

    assert response.status_code == 400
    assert "password-protected" in response.get_json()["error"]["message"]


def test_file_just_over_20_mb_is_rejected(client, upload_dir):
    register(client)

    response = upload(client, b"%PDF-" + b"0" * MAX_UPLOAD_BYTES)

    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "file_too_large"
    assert stored_files(upload_dir) == []


def test_request_far_over_the_limit_is_cut_off_while_reading(client):
    register(client)

    response = upload(client, b"%PDF-" + b"0" * (MAX_UPLOAD_BYTES * 2))

    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "request_entity_too_large"


def test_other_endpoints_keep_the_1_mb_body_limit(client):
    response = client.post(
        "/api/auth/login", data=b"x" * (2 * 1024 * 1024), content_type="application/json"
    )

    assert response.status_code == 413


def test_uploads_are_rate_limited_per_user(db_engine, test_database_url, upload_dir):
    app = make_integration_app(test_database_url, upload_dir, rate_limit_upload="2 per hour")
    alice, bob = api_client(app), api_client(app)
    register(alice, "alice@example.com")
    register(bob, "bob@example.com")

    statuses = [upload(alice, LECTURE).status_code for _ in range(3)]

    assert statuses == [202, 202, 429]
    # Same IP address, different user: Bob has his own allowance.
    assert upload(bob, LECTURE).status_code == 202


def test_document_row_records_the_page_count_and_random_filename(client, db_engine):
    register(client)
    upload(client, LECTURE, "Week 7.pdf")

    with Session(db_engine) as db:
        document = db.scalars(select(Document)).one()

    assert document.page_count == 3
    assert document.original_filename == "Week 7.pdf"
    assert document.stored_filename.endswith(".pdf") and document.stored_filename != "Week 7.pdf"
