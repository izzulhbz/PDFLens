from app import create_app
from tests.conftest import fake_ollama, make_settings, unreachable_ollama


def test_ready_when_database_and_ollama_are_up(client):
    response = client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "checks": {"database": "ok", "ollama": "ok"},
    }


def test_still_ready_but_reports_it_when_ollama_is_down(db_engine, test_database_url):
    app = create_app(
        make_settings(database_url=test_database_url), ollama_http=unreachable_ollama()
    )

    response = app.test_client().get("/api/health/ready")

    assert response.status_code == 200
    assert response.get_json()["checks"] == {"database": "ok", "ollama": "unreachable"}


def test_reports_when_embedding_model_is_not_pulled(db_engine, test_database_url):
    app = create_app(
        make_settings(database_url=test_database_url), ollama_http=fake_ollama("llama3.2:1b")
    )

    response = app.test_client().get("/api/health/ready")

    assert response.get_json()["checks"]["ollama"] == "embed_model_missing"
