"""Input validation on the auth endpoints.

These run against an app with no reachable database, which also proves
that bad input is rejected before any database work or password hashing.
"""

import pytest

from app.api.auth import MAX_PASSWORD_LENGTH, normalise_email


@pytest.mark.parametrize(
    "body",
    [
        None,  # not JSON at all
        ["alice@example.com", "a password"],  # JSON, but not an object
        {"email": "alice@example.com"},  # no password
        {"email": "", "password": "correct horse battery"},
        {"email": 42, "password": "correct horse battery"},
        {"email": "alice@example.com", "password": "x" * (MAX_PASSWORD_LENGTH + 1)},
    ],
)
@pytest.mark.parametrize("endpoint", ["/api/auth/register", "/api/auth/login"])
def test_malformed_credentials_are_400(unit_client, endpoint, body):
    if body is None:
        response = unit_client.post(endpoint, data="email=a&password=b")
    else:
        response = unit_client.post(endpoint, json=body)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "two words@example.com", "@example.com"])
def test_register_rejects_invalid_email(unit_client, email):
    response = unit_client.post(
        "/api/auth/register", json={"email": email, "password": "correct horse battery"}
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_email"


def test_register_rejects_short_password(unit_client):
    response = unit_client.post(
        "/api/auth/register", json={"email": "alice@example.com", "password": "short-pass1"}
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "weak_password"


def test_email_is_trimmed_and_lowercased():
    assert normalise_email("  Alice@Example.COM ") == "alice@example.com"
