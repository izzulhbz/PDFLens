"""Document summaries. Both endpoints require a logged-in user.

GET  /api/documents/<id>/summary  -> 200 the saved summary, or 404 if none yet
POST /api/documents/<id>/summary  {"provider"?, "prefer"?, "tone"?, "length"?,
                                   "include_charts"?}
                                  -> 200 a newly written summary

tone is professional, simple, friendly or academic; length is brief,
standard or detailed; include_charts asks for charts of numeric data the
document contains. Anything outside those values is a 400.

The frontend calls GET when a document is opened and POST only if there is
no summary yet (or the user clicks Regenerate), so each document normally
costs one model call, not one per visit.
"""

import logging
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from app.api.provider_choice import read_provider_choice
from app.db import get_session
from app.errors import ApiError
from app.llm.base import LLMError
from app.models import Document, DocumentStatus
from app.rag.summary import (
    DEFAULT_OPTIONS,
    LENGTHS,
    TONES,
    SummaryError,
    SummaryOptions,
    generate_summary,
)
from app.security.access import owned_document
from app.security.rate_limit import limit_from_settings, limiter, user_or_ip
from app.security.sessions import login_required

logger = logging.getLogger(__name__)

bp = Blueprint("summary", __name__, url_prefix="/api/documents")


@bp.get("/<int:document_id>/summary")
@login_required
def get_summary(document_id: int) -> Response:
    document = owned_document(document_id)
    if document.summary is None:
        raise ApiError(404, "summary_not_found", "This document has no summary yet.")
    return jsonify(_summary_json(document))


@bp.post("/<int:document_id>/summary")
@limiter.limit(limit_from_settings("rate_limit_summary"), key_func=user_or_ip)
@login_required
def create_summary(document_id: int) -> Response:
    provider, prefer, options = _read_request()
    document = owned_document(document_id)
    if document.status != DocumentStatus.READY:
        raise ApiError(409, "document_not_ready", f"This document is {document.status}.")

    try:
        generate_summary(
            get_session(),
            document,
            current_app.extensions["llm_router"],
            provider,
            options,
            prefer=prefer,
        )
    except LLMError as exc:
        logger.warning("summary.failed document_id=%s error=%r", document.id, str(exc))
        raise ApiError(
            503,
            "llm_unavailable",
            "The AI provider couldn't write a summary right now. Try again, or pick another "
            "provider.",
        ) from None
    except SummaryError as exc:
        logger.warning("summary.invalid document_id=%s error=%r", document.id, str(exc))
        raise ApiError(
            502,
            "summary_invalid",
            "The model's summary came back in an unusable form. Try again, or pick another "
            "provider.",
        ) from None
    return jsonify(_summary_json(document))


def _read_request() -> tuple[str | None, str | None, SummaryOptions]:
    data: Any = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_request", "Send a JSON object.")
    provider, prefer = read_provider_choice(data)

    # Allowlists, like the provider: each value picks instructions written
    # on the server, so nothing the client sends is pasted into the prompt.
    defaults = DEFAULT_OPTIONS
    tone = data.get("tone", defaults.tone)
    if tone not in TONES:
        raise ApiError(400, "invalid_option", f"tone must be one of {list(TONES)}.")
    length = data.get("length", defaults.length)
    if length not in LENGTHS:
        raise ApiError(400, "invalid_option", f"length must be one of {list(LENGTHS)}.")
    include_charts = data.get("include_charts", defaults.include_charts)
    if not isinstance(include_charts, bool):
        raise ApiError(400, "invalid_option", "include_charts must be true or false.")
    options = SummaryOptions(tone=tone, length=length, include_charts=include_charts)
    return provider, prefer, options


def _summary_json(document: Document) -> dict[str, Any]:
    return {
        "summary": document.summary,
        "options": document.summary_options,
        "provider": document.summary_provider,
        "created_at": document.summary_created_at.isoformat()
        if document.summary_created_at
        else None,
    }
