"""Question answering and provider status. Both require a logged-in user.

POST /api/ask        {"document_id", "question", "provider"?} -> 200 answer
GET  /api/providers  -> which LLM providers can be used right now

The optional "provider" is checked against an allowlist (anthropic, ollama,
auto). Anything else is a 400, never passed on, so a client can't make the
server call an arbitrary model or provider.
"""

import logging
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from app.api.documents import answer_json
from app.db import get_session
from app.embeddings.base import EmbeddingError
from app.errors import ApiError
from app.llm.base import PROVIDERS, LLMError
from app.llm.router import LLMRouter
from app.models import DocumentStatus
from app.rag.qa import answer_question
from app.security.access import owned_document
from app.security.rate_limit import limit_from_settings, limiter, user_or_ip
from app.security.sessions import current_user, login_required

logger = logging.getLogger(__name__)

bp = Blueprint("ask", __name__, url_prefix="/api")

MAX_QUESTION_LENGTH = 2000


@bp.post("/ask")
@limiter.limit(limit_from_settings("rate_limit_ask"), key_func=user_or_ip)
@login_required
def ask() -> Response:
    document_id, question, provider = _read_ask_request()
    document = owned_document(document_id)
    if document.status != DocumentStatus.READY:
        raise ApiError(409, "document_not_ready", f"This document is {document.status}.")

    settings = current_app.extensions["settings"]
    try:
        answer = answer_question(
            get_session(),
            user_id=current_user().id,
            document_id=document.id,
            question=question,
            embedder=current_app.extensions["embedder"],
            router=current_app.extensions["llm_router"],
            requested_provider=provider,
            top_k=settings.retrieval_top_k,
        )
    except EmbeddingError as exc:
        raise ApiError(503, "embedding_unavailable", exc.user_message) from None
    except LLMError as exc:
        logger.warning("ask.failed document_id=%s error=%r", document.id, str(exc))
        raise ApiError(
            503,
            "llm_unavailable",
            "The AI provider couldn't answer right now. Try again, or pick another provider.",
        ) from None

    return jsonify(answer_json(answer))


@bp.get("/providers")
@login_required
def providers() -> Response:
    router: LLMRouter = current_app.extensions["llm_router"]
    settings = current_app.extensions["settings"]
    anthropic_ok, anthropic_detail = router.anthropic.availability()
    ollama_ok, ollama_detail = router.ollama.availability()
    return jsonify(
        default=router.default,
        providers=[
            {
                "name": "anthropic",
                "model": settings.anthropic_model,
                "available": anthropic_ok,
                "detail": anthropic_detail,
            },
            {
                "name": "ollama",
                "model": settings.ollama_chat_model,
                "available": ollama_ok,
                "detail": ollama_detail,
            },
            {
                "name": "auto",
                "model": None,
                "available": anthropic_ok or ollama_ok,
                "detail": _auto_detail(anthropic_ok, ollama_ok),
            },
        ],
    )


def _auto_detail(anthropic_ok: bool, ollama_ok: bool) -> str:
    if anthropic_ok and ollama_ok:
        return "Anthropic, falling back to Ollama"
    if anthropic_ok:
        return "Anthropic only (Ollama unavailable)"
    if ollama_ok:
        return "Ollama only (Anthropic unavailable)"
    return "No provider available"


def _read_ask_request() -> tuple[int, str, str | None]:
    data: Any = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_request", "Send a JSON object.")

    document_id = data.get("document_id")
    # bool is a subclass of int in Python, so rule it out explicitly.
    if not isinstance(document_id, int) or isinstance(document_id, bool) or document_id < 1:
        raise ApiError(400, "invalid_request", "document_id must be a positive integer.")

    question = data.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ApiError(400, "invalid_request", "question is required.")
    question = question.strip()
    if len(question) > MAX_QUESTION_LENGTH:
        raise ApiError(
            400, "invalid_request", f"Keep questions under {MAX_QUESTION_LENGTH} characters."
        )

    provider = data.get("provider")
    if provider is not None and provider not in PROVIDERS:
        raise ApiError(400, "invalid_provider", f"provider must be one of {list(PROVIDERS)}.")
    return document_id, question, provider
