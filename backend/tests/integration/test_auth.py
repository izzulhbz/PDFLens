"""Register, log in, log out and session handling, against real Postgres."""

import logging
import time

from argon2 import PasswordHasher
from flask.sessions import SecureCookieSessionInterface
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import create_app
from app.models import User
from app.security.sessions import SESSION_COOKIE_NAME
from tests.conftest import (
    TEST_PASSWORD,
    api_client,
    fake_ollama,
    make_integration_app,
    make_settings,
    register,
)


def login(client, email="alice@example.com", password=TEST_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# --- Register ---------------------------------------------------------------------------


def test_register_creates_account_and_logs_in(client, db_engine):
    response = client.post(
        "/api/auth/register", json={"email": " Alice@Example.com ", "password": TEST_PASSWORD}
    )

    assert response.status_code == 201
    assert response.get_json()["user"]["email"] == "alice@example.com"
    assert client.get("/api/auth/me").get_json()["user"]["email"] == "alice@example.com"


def test_password_is_stored_as_argon2id_hash(client, db_engine):
    register(client)

    with Session(db_engine) as db:
        stored = db.scalars(select(User.password_hash)).one()

    assert stored.startswith("$argon2id$")
    assert TEST_PASSWORD not in stored


def test_register_with_existing_email_is_409_regardless_of_case(client):
    register(client, "alice@example.com")

    response = client.post(
        "/api/auth/register", json={"email": "ALICE@example.com", "password": TEST_PASSWORD}
    )

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "email_taken"


# --- Login -----------------------------------------------------------------------------


def test_login_with_correct_password(app, client):
    register(client)
    fresh_client = api_client(app)

    response = login(fresh_client)

    assert response.status_code == 200
    assert fresh_client.get("/api/auth/me").status_code == 200


def test_wrong_password_and_unknown_email_get_identical_responses(client):
    register(client)

    wrong_password = login(client, password="not the right password")
    unknown_email = login(client, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.get_json() == unknown_email.get_json()


def test_unknown_email_takes_about_as_long_as_wrong_password(client):
    # Without the dummy hash, an unknown email would answer in ~1 ms and a
    # wrong password in ~50 ms, revealing which emails have accounts.
    register(client)

    def timed(email):
        start = time.perf_counter()
        login(client, email=email, password="not the right password")
        return time.perf_counter() - start

    unknown, known = timed("nobody@example.com"), timed("alice@example.com")

    assert unknown > known * 0.5


def test_failed_login_log_has_no_password_or_email(client, caplog):
    register(client)

    with caplog.at_level(logging.INFO):
        login(client, password="my secret attempt")

    assert "auth.login_failed reason=wrong_password" in caplog.text
    assert "my secret attempt" not in caplog.text
    assert "alice@example.com" not in caplog.text


def test_login_upgrades_a_weak_hash(client, db_engine):
    weak_hash = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(TEST_PASSWORD)
    with Session(db_engine) as db:
        db.add(User(email="old@example.com", password_hash=weak_hash))
        db.commit()

    assert login(client, email="old@example.com").status_code == 200

    with Session(db_engine) as db:
        upgraded = db.scalars(select(User.password_hash)).one()
    assert upgraded != weak_hash
    assert "m=65536,t=3,p=4" in upgraded


def test_login_is_rate_limited(client):
    register(client)
    statuses = [login(client, password="wrong guess number").status_code for _ in range(6)]

    # The default limit is 5 per minute.
    assert statuses == [401] * 5 + [429]


WRONG_PASSWORD = "wrong guess number"


def from_ip(client, address, password, email="alice@example.com"):
    """A login attempt arriving from `address`, as if from another machine."""
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        environ_base={"REMOTE_ADDR": address},
    )


def test_guesses_spread_over_many_ips_are_limited_per_account(
    db_engine, test_database_url, upload_dir
):
    app = make_integration_app(test_database_url, upload_dir, rate_limit_login_account="3 per hour")
    client = api_client(app)
    register(client)

    statuses = [from_ip(client, f"10.0.0.{i}", WRONG_PASSWORD).status_code for i in range(4)]
    # Even the right password is refused for now, from yet another IP.
    correct = from_ip(client, "10.0.0.99", password=TEST_PASSWORD).status_code

    assert statuses == [401, 401, 401, 429]
    assert correct == 429


def test_the_account_limit_counts_failures_only_and_per_account(
    db_engine, test_database_url, upload_dir
):
    app = make_integration_app(test_database_url, upload_dir, rate_limit_login_account="3 per hour")
    client = api_client(app)
    register(client)
    register(api_client(app), "bob@example.com")

    successes = [from_ip(client, f"10.0.1.{i}", TEST_PASSWORD).status_code for i in range(5)]
    for i in range(3):
        from_ip(client, f"10.0.2.{i}", WRONG_PASSWORD, email="bob@example.com")

    assert successes == [200] * 5
    assert from_ip(client, "10.0.3.1", TEST_PASSWORD, email=" ALICE@example.com").status_code == 200
    assert from_ip(client, "10.0.3.2", TEST_PASSWORD, email="bob@example.com").status_code == 429


# --- Sessions ------------------------------------------------------------------------------


def test_logout_ends_the_session(client):
    register(client)

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_logout_revokes_a_copy_of_the_cookie_stolen_before_it(app, client):
    register(client)
    stolen = api_client(app)
    stolen.set_cookie(SESSION_COOKIE_NAME, client.get_cookie(SESSION_COOKIE_NAME).value)
    assert stolen.get("/api/auth/me").status_code == 200  # the copy works...

    client.post("/api/auth/logout")

    assert stolen.get("/api/auth/me").status_code == 401  # ...until the user logs out


def test_logout_signs_the_user_out_on_every_device(app, client):
    register(client)
    laptop = api_client(app)
    laptop.post("/api/auth/login", json={"email": "alice@example.com", "password": TEST_PASSWORD})

    client.post("/api/auth/logout")

    assert laptop.get("/api/auth/me").status_code == 401


def test_logging_in_again_after_logout_works(client):
    register(client)
    client.post("/api/auth/logout")

    client.post("/api/auth/login", json={"email": "alice@example.com", "password": TEST_PASSWORD})

    assert client.get("/api/auth/me").status_code == 200


def test_logout_with_a_revoked_cookie_changes_nothing(app, client, db_engine):
    register(client)
    stolen = api_client(app)
    stolen.set_cookie(SESSION_COOKIE_NAME, client.get_cookie(SESSION_COOKIE_NAME).value)
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "alice@example.com", "password": TEST_PASSWORD})

    # The old copy can't be used to log the user out of their new session.
    stolen.post("/api/auth/logout")

    assert client.get("/api/auth/me").status_code == 200


def test_session_cookie_signed_with_another_key_is_rejected(client, test_database_url):
    user_id = register(client)
    # An attacker who doesn't know SECRET_KEY signs a cookie claiming to be
    # this user, using a key of their own.
    attacker_app = create_app(
        make_settings(test_database_url, secret_key="attacker-key-" + "x" * 32),
        ollama_http=fake_ollama(),
    )
    forged = SecureCookieSessionInterface().get_signing_serializer(attacker_app)
    assert forged is not None
    client.set_cookie(SESSION_COOKIE_NAME, forged.dumps({"user_id": user_id}))

    assert client.get("/api/auth/me").status_code == 401


def test_session_expires_after_its_lifetime(client, monkeypatch):
    register(client)
    nine_hours_later = time.time() + 9 * 3600
    # itsdangerous checks the cookie's signed timestamp against the clock.
    monkeypatch.setattr("itsdangerous.timed.time.time", lambda: nine_hours_later)

    assert client.get("/api/auth/me").status_code == 401


def test_session_of_deleted_user_is_rejected(client, db_engine):
    register(client)
    with Session(db_engine) as db:
        db.delete(db.scalars(select(User)).one())
        db.commit()

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    # The stale cookie is cleared, too.
    assert f"{SESSION_COOKIE_NAME}=;" in response.headers["Set-Cookie"]
