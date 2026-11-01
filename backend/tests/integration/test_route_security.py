"""Every API route, found from the app's URL map, is checked for login and ownership.

Each endpoint also has its own tests, but these don't rely on anyone
remembering to write them: a new route that forgets @login_required or
owned_document() fails here as soon as it's registered.
"""

import pytest
from flask import Flask
from sqlalchemy.orm import Session

from app.models import Document
from tests.conftest import api_client, register, upload
from tests.pdf_factory import make_pdf

# The only routes anyone may call without logging in.
PUBLIC_ROUTES = {
    ("GET", "/api/health"),
    ("GET", "/api/health/ready"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
}
LECTURE = make_pdf(["Embeddings turn text into vectors.", "HNSW builds a layered graph."])


def api_routes(app: Flask) -> list[tuple[str, str]]:
    """(method, rule) for every API route, e.g. ("GET", "/api/documents/<int:document_id>")."""
    routes = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        for method in sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}):
            routes.append((method, rule.rule))
    return routes


def url_for_document(rule: str, document_id: int) -> str:
    url = rule.replace("<int:document_id>", str(document_id))
    assert "<" not in url, f"{rule}: add its URL parameter to this test"
    return url


def call(client, method: str, url: str, document_id: int):
    # A body that would be valid for any of the JSON endpoints.
    body = {"document_id": document_id, "question": "What is HNSW?"}
    return client.open(url, method=method, json=body)


def test_the_route_list_is_found(app):
    # Guards the tests below: an empty list would make them pass vacuously.
    routes = api_routes(app)

    assert len(routes) >= 14
    assert set(routes) >= PUBLIC_ROUTES


def test_every_non_public_route_requires_login(app, client):
    register(client)
    document_id = upload(client, LECTURE).get_json()["document"]["id"]
    anonymous = api_client(app)

    for method, rule in api_routes(app):
        if (method, rule) in PUBLIC_ROUTES:
            continue
        response = call(anonymous, method, url_for_document(rule, document_id), document_id)
        assert response.status_code == 401, f"{method} {rule} answered {response.status_code}"


@pytest.mark.parametrize("victim_status", ["ready", "processing"])
def test_no_route_touches_another_users_document(app, client, db_engine, victim_status):
    register(client)
    document_id = upload(client, LECTURE).get_json()["document"]["id"]
    with Session(db_engine) as db:
        db.get_one(Document, document_id).status = victim_status
        db.commit()
    mallory = api_client(app)
    register(mallory, "mallory@example.com")

    checked = 0
    for method, rule in api_routes(app):
        if "<int:document_id>" not in rule and rule != "/api/ask":
            continue
        response = call(mallory, method, url_for_document(rule, document_id), document_id)
        # 404, exactly as for a document that doesn't exist: not 403, which
        # would confirm the ID is in use.
        assert response.status_code == 404, f"{method} {rule} answered {response.status_code}"
        checked += 1

    assert checked >= 6
    # Still there, and still Alice's.
    assert client.get(f"/api/documents/{document_id}").status_code == 200
