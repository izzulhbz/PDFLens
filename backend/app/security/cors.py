"""CORS: which other websites may call this API from a browser.

By default a browser won't let a page on one origin read responses from
another origin. A server can opt in with Access-Control-Allow-* headers.
We opt in only for the exact origins in CORS_ALLOWED_ORIGINS, and never
with a wildcard, because these requests carry the user's session cookie.
The list is empty by default: the React app is served from the same origin
as the API (through Nginx in Docker, and the Vite proxy in dev mode).

For any origin not on the list, no CORS headers are sent. The browser then
blocks the page from reading the response and refuses to send requests
that need a preflight, such as any request with our CSRF header.
"""

from flask import Flask, Response, request

from app.security.csrf import CSRF_HEADER

ALLOWED_METHODS = "GET, POST, DELETE"
ALLOWED_HEADERS = f"Content-Type, {CSRF_HEADER}"
PREFLIGHT_MAX_AGE_SECONDS = "600"


def register_cors(app: Flask, allowed_origins: tuple[str, ...]) -> None:
    allowed = frozenset(allowed_origins)

    @app.before_request
    def answer_preflight() -> Response | None:
        # A preflight is the OPTIONS request a browser sends before a
        # cross-origin request with custom headers, asking for permission.
        # Answer it here; add_cors_headers decides whether to grant it.
        if request.method == "OPTIONS" and "Access-Control-Request-Method" in request.headers:
            return Response(status=204)
        return None

    @app.after_request
    def add_cors_headers(response: Response) -> Response:
        # Responses differ by Origin, so caches must not reuse one across origins.
        response.vary.add("Origin")
        origin = request.headers.get("Origin")
        if origin in allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            if request.method == "OPTIONS":
                response.headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
                response.headers["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
                response.headers["Access-Control-Max-Age"] = PREFLIGHT_MAX_AGE_SECONDS
        return response
