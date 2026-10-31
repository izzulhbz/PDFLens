"""Security headers on every API response.

The API only ever returns JSON, so the strictest settings cost nothing:
- Content-Security-Policy "default-src 'none'": if a response were ever
  opened as a page, it could load nothing and run no scripts.
  "frame-ancestors 'none'" (and the older X-Frame-Options: DENY) stop other
  sites from showing it in a frame, which blocks clickjacking.
- X-Content-Type-Options: nosniff: browsers must trust our Content-Type and
  never guess that a JSON response is HTML or JavaScript.
- Referrer-Policy: no-referrer: our URLs are never leaked to other sites.
- Cache-Control: no-store: responses holding a user's data are never kept
  in browser or proxy caches.
- Cross-Origin-Resource-Policy: same-origin: other sites can't embed our
  responses with <script> or <img> tags.

Nginx sets its own, wider policy for the React app (Phase 5). HSTS belongs
on whichever proxy terminates HTTPS, since this stack runs plain HTTP locally.
"""

from flask import Flask, Response

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def register_security_headers(app: Flask) -> None:
    @app.after_request
    def add_security_headers(response: Response) -> Response:
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response
