"""App behaviour that needs no database: health, errors and request logging."""

import logging
import re

from app import create_app
from tests.conftest import fake_ollama, make_settings, unreachable_ollama


def test_liveness_needs_no_database(unit_client):
    response = unit_client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_every_response_has_a_request_id(unit_client):
    response = unit_client.get("/api/health")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_readiness_is_503_when_database_is_down(unit_client, database_down):
    response = unit_client.get("/api/health/ready")

    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == "unreachable"


def test_readiness_reports_ollama_down(database_down):
    app = create_app(make_settings(), ollama_http=unreachable_ollama())

    body = app.test_client().get("/api/health/ready").get_json()

    assert body["checks"]["ollama"] == "unreachable"


def test_readiness_reports_missing_embedding_model(database_down):
    app = create_app(make_settings(), ollama_http=fake_ollama("llama3.2:latest"))

    body = app.test_client().get("/api/health/ready").get_json()

    assert body["checks"]["ollama"] == "embed_model_missing"


def test_unknown_route_returns_json_error(unit_client):
    response = unit_client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_unexpected_error_hides_details_from_client(unit_app):
    def explode():
        raise RuntimeError("secret internal detail")

    unit_app.add_url_rule("/boom", view_func=explode)

    response = unit_app.test_client().get("/boom")

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in response.get_data(as_text=True)


def test_request_log_has_route_but_not_query_string(unit_client, caplog):
    with caplog.at_level(logging.INFO, logger="pdflens.request"):
        unit_client.get("/api/health?password=hunter2")

    logged = caplog.text
    assert "route=/api/health " in logged
    assert "hunter2" not in logged


def test_request_log_strips_newlines_from_unmatched_paths(unit_client, caplog):
    # %0A is a newline. Logged raw, it would let a client forge a log line.
    with caplog.at_level(logging.INFO, logger="pdflens.request"):
        unit_client.get("/api/x%0Astatus=200 forged")

    [record] = [r for r in caplog.records if r.name == "pdflens.request"]
    assert "\n" not in record.getMessage()
