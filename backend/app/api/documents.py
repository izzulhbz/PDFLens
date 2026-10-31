"""Document endpoints. All of them require a logged-in user.

POST /api/documents          multipart field "file" (a PDF) -> 202 {"document"}
GET  /api/documents          -> 200 {"documents": [...]}, newest first
GET  /api/documents/<id>     -> 200 {"document"}, or 404

Uploading returns 202 Accepted with status "processing": the slow work
(parsing and embedding) happens in the background (see ingestion/worker.py).
The client polls GET /api/documents/<id> until the status is "ready" or
"failed".
"""

import logging
import re
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import select

from app.db import get_session
from app.errors import ApiError
from app.ingestion.pdf import InvalidPdfError, validate_pdf
from app.models import Document, DocumentStatus
from app.security.access import owned_document
from app.security.rate_limit import limit_from_settings, limiter, user_or_ip
from app.security.sessions import current_user, login_required
from app.storage import UploadStore

logger = logging.getLogger(__name__)

bp = Blueprint("documents", __name__, url_prefix="/api/documents")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# A multipart request is slightly bigger than the file it carries.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_FILENAME_LENGTH = 255
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@bp.post("")
@limiter.limit(limit_from_settings("rate_limit_upload"), key_func=user_or_ip)
@login_required
def upload_document() -> tuple[Response, int]:
    # Raise the body-size limit for this endpoint only (the app-wide limit
    # is 1 MB). Werkzeug then rejects anything bigger with a 413 while
    # reading the request, before the whole body has been received.
    request.max_content_length = MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApiError(400, "file_missing", "Attach a PDF in the 'file' form field.")
    filename = display_filename(upload.filename)
    if not filename.lower().endswith(".pdf"):
        raise ApiError(400, "invalid_file_type", "Only PDF files are accepted.")

    data = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "file_too_large", "PDFs can be at most 20 MB.")
    try:
        page_count = validate_pdf(data)
    except InvalidPdfError as exc:
        raise ApiError(400, "invalid_pdf", str(exc)) from None

    store: UploadStore = current_app.extensions["upload_store"]
    stored_filename = store.save(data)
    document = Document(
        user_id=current_user().id,
        original_filename=filename,
        stored_filename=stored_filename,
        page_count=page_count,
        status=DocumentStatus.PROCESSING,
    )
    db = get_session()
    db.add(document)
    try:
        db.commit()
    except Exception:
        # Don't leave an orphaned file on disk if the database write fails.
        store.delete(stored_filename)
        raise

    logger.info(
        "document.uploaded document_id=%s pages=%s bytes=%s", document.id, page_count, len(data)
    )
    current_app.extensions["ingestion"].submit(document.id)
    db.refresh(document)  # the worker may already have changed the status
    return jsonify(document=document_json(document)), 202


@bp.get("")
@login_required
def list_documents() -> Response:
    documents = get_session().scalars(
        select(Document)
        .where(Document.user_id == current_user().id)
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    return jsonify(documents=[document_json(d) for d in documents])


@bp.get("/<int:document_id>")
@login_required
def get_document(document_id: int) -> Response:
    return jsonify(document=document_json(owned_document(document_id)))


def display_filename(raw: str) -> str:
    """The client's filename, made safe to store and display (never used as a path)."""
    # Some browsers send the full path, e.g. C:\\Users\\me\\notes.pdf.
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    name = _CONTROL_CHARS.sub("", name).strip()
    return name[:MAX_FILENAME_LENGTH] or "document.pdf"


def document_json(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "filename": document.original_filename,
        "page_count": document.page_count,
        "status": document.status,
        "error_message": document.error_message,
        "created_at": document.created_at.isoformat(),
    }
