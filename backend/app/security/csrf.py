"""CSRF protection for cookie-authenticated requests.

Cross-site request forgery: a malicious website makes the victim's browser
send a request to our API, and the browser attaches the session cookie
automatically. Two layers stop this:

1. SameSite=Lax on the session cookie (sessions.py): browsers don't attach
   it to cross-site POST, PUT, PATCH or DELETE requests.
2. Every state-changing request must carry the header X-PDFLens-CSRF: 1.
   An HTML form on another site can't set custom headers, and JavaScript on
   another site may only set one after a CORS preflight, which our CORS
   policy refuses (cors.py). Our own frontend adds the header to every
   request.

This is OWASP's "custom request header" defence. It needs no token to
store or compare: the attacker can't send the header at all, so there is
nothing to guess. It relies on one rule elsewhere: GET requests must never
change anything.
"""

from flask import Flask, request

from app.errors import ApiError

CSRF_HEADER = "X-PDFLens-CSRF"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def register_csrf_protection(app: Flask) -> None:
    @app.before_request
    def require_csrf_header() -> None:
        if request.method in SAFE_METHODS:
            return
        if request.headers.get(CSRF_HEADER) != "1":
            raise ApiError(403, "csrf_header_missing", f"Missing the {CSRF_HEADER} header.")
