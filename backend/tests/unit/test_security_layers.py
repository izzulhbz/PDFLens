"""CSRF, CORS, security headers, cookies and rate limiting. No database needed."""

from flask import session

from app import create_app
from tests.conftest import api_client, fake_ollama, make_settings

ALLOWED_ORIGIN = "http://127.0.0.1:5173"


def make_app(**overrides):
    return create_app(make_settings(**overrides), ollama_http=fake_ollama())


# --- CSRF ------------------------------------------------------------------------


def test_post_without_csrf_header_is_rejected(unit_app):
    response = unit_app.test_client().post("/api/auth/logout")

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "csrf_header_missing"


def test_post_with_csrf_header_is_allowed(unit_client):
    assert unit_client.post("/api/auth/logout").status_code == 204


def test_get_needs_no_csrf_header(unit_app):
    assert unit_app.test_client().get("/api/health").status_code == 200


# --- CORS --------------------------------------------------------------------------


def test_preflight_from_allowed_origin_is_granted():
    client = make_app(cors_allowed_origins=(ALLOWED_ORIGIN,)).test_client()

    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, x-pdflens-csrf",
        },
    )

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert "X-PDFLens-CSRF" in response.headers["Access-Control-Allow-Headers"]


def test_other_origins_get_no_cors_headers():
    client = make_app(cors_allowed_origins=(ALLOWED_ORIGIN,)).test_client()

    response = client.options(
        "/api/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    # Without Access-Control-Allow-Origin, the browser refuses the request.
    assert "Access-Control-Allow-Origin" not in response.headers


def test_no_origins_are_allowed_by_default(unit_app):
    response = unit_app.test_client().get("/api/health", headers={"Origin": ALLOWED_ORIGIN})

    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Origin" in response.headers["Vary"]


# --- Security headers ---------------------------------------------------------------


def test_security_headers_on_success_and_error_responses(unit_client):
    for path in ("/api/health", "/api/does-not-exist"):
        headers = unit_client.get(path).headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Content-Security-Policy"].startswith("default-src 'none'")
        assert headers["Cache-Control"] == "no-store"
        assert headers["Referrer-Policy"] == "no-referrer"


# --- Session cookie flags --------------------------------------------------------


def _set_cookie_header(app):
    @app.get("/test-set-session")
    def set_session():
        session["probe"] = 1
        return "ok"

    return app.test_client().get("/test-set-session").headers["Set-Cookie"]


def test_session_cookie_is_httponly_samesite_lax_and_secure_by_default():
    cookie = _set_cookie_header(make_app(session_cookie_secure=True))

    assert cookie.startswith("pdflens_session=")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" in cookie


def test_secure_flag_can_be_turned_off_for_local_http():
    assert "Secure" not in _set_cookie_header(make_app(session_cookie_secure=False))


# --- Auth without a session ------------------------------------------------------------


def test_me_without_a_session_is_401(unit_client):
    response = unit_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


# --- Rate limiting ------------------------------------------------------------------------


def test_login_is_rate_limited_per_ip():
    client = api_client(make_app(rate_limit_login="2 per minute"))

    # Invalid bodies are rejected before any database access, but they
    # still count towards the limit.
    statuses = [client.post("/api/auth/login", json={}).status_code for _ in range(3)]

    assert statuses == [400, 400, 429]


def test_rate_limit_response_is_json_with_retry_after():
    client = api_client(make_app(rate_limit_register="1 per minute"))
    client.post("/api/auth/register", json={})

    response = client.post("/api/auth/register", json={})

    assert response.status_code == 429
    assert response.get_json()["error"]["code"] == "too_many_requests"
    assert int(response.headers["Retry-After"]) > 0


def test_limits_are_counted_per_client_ip():
    app = make_app(rate_limit_login="1 per minute")
    first = api_client(app)
    second = api_client(app)
    second.environ_base["REMOTE_ADDR"] = "10.0.0.2"

    first.post("/api/auth/login", json={})

    assert first.post("/api/auth/login", json={}).status_code == 429
    assert second.post("/api/auth/login", json={}).status_code == 400


def test_forwarded_ip_is_ignored_unless_a_proxy_is_trusted():
    # With no trusted proxy, a client can't escape its limit by inventing
    # an X-Forwarded-For address on each request.
    client = api_client(make_app(rate_limit_login="1 per minute"))

    client.post("/api/auth/login", json={}, headers={"X-Forwarded-For": "1.1.1.1"})
    response = client.post("/api/auth/login", json={}, headers={"X-Forwarded-For": "2.2.2.2"})

    assert response.status_code == 429


def test_forwarded_ip_is_used_behind_a_trusted_proxy():
    client = api_client(make_app(rate_limit_login="1 per minute", trusted_proxy_count=1))

    client.post("/api/auth/login", json={}, headers={"X-Forwarded-For": "1.1.1.1"})
    response = client.post("/api/auth/login", json={}, headers={"X-Forwarded-For": "2.2.2.2"})

    assert response.status_code == 400
