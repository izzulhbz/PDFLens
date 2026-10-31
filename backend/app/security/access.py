"""Authorisation: users can only reach their own documents.

This guards against IDOR (insecure direct object reference): document IDs
are sequential numbers in URLs, so anyone could try /api/documents/1,
/api/documents/2, and so on. Every lookup therefore filters on the document
ID *and* the logged-in user's ID in one query. Fetching by ID first and
checking the owner afterwards would also work, but it's easy to forget the
second step in one endpoint; one shared helper makes the safe way the only way.

Someone else's document gets the same 404 as one that doesn't exist (not a
403), so the response doesn't even confirm that the ID is in use.
"""

from sqlalchemy import select

from app.db import get_session
from app.errors import ApiError
from app.models import Document
from app.security.sessions import current_user


def owned_document(document_id: int) -> Document:
    """The current user's document with this ID, or a 404. Use inside @login_required views."""
    document = (
        get_session()
        .scalars(
            select(Document).where(
                Document.id == document_id, Document.user_id == current_user().id
            )
        )
        .one_or_none()
    )
    if document is None:
        raise ApiError(404, "document_not_found", "Document not found.")
    return document
