"""Account endpoints.

POST /api/auth/register  {"email", "password"} -> 201 {"user"}, and logged in
POST /api/auth/login     {"email", "password"} -> 200 {"user"}, and logged in
POST /api/auth/logout                          -> 204
GET  /api/auth/me                              -> 200 {"user"}, or 401

Login failures always return the same 401 message, whether the email is
unknown or the password is wrong, and take the same time (see
passwords.spend_equal_time), so the endpoint doesn't reveal which emails
have accounts.
"""

import logging
import re
from typing import Any

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import get_session
from app.errors import ApiError
from app.models import User
from app.security.passwords import hash_password, needs_rehash, spend_equal_time, verify_password
from app.security.rate_limit import failed_login, limit_from_settings, limiter, login_account
from app.security.sessions import current_user, log_in, log_out, login_required

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

MAX_EMAIL_LENGTH = 320  # the longest address SMTP allows
# Length is what makes a password strong, so there are no "must contain a
# digit" rules (NIST SP 800-63B advises against them).
MIN_PASSWORD_LENGTH = 12
# Argon2 accepts any length. The cap stops someone posting megabytes of
# "password" just to keep the server busy hashing it.
MAX_PASSWORD_LENGTH = 128
# Deliberately loose: something@something.something with no spaces. The
# only real proof that an address works is sending it an email.
_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

INVALID_CREDENTIALS = "Invalid email or password."


@bp.post("/register")
@limiter.limit(limit_from_settings("rate_limit_register"))
def register() -> tuple[Response, int]:
    email, password = _read_credentials()
    _validate_new_account(email, password)

    db = get_session()
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Rely on the UNIQUE constraint rather than checking first with a
        # SELECT: two simultaneous sign-ups could both pass a check, but
        # only one can pass the constraint.
        if "uq_users_email" not in str(exc.orig):
            raise
        # Saying so is unavoidable for a usable sign-up form, though it does
        # reveal that the address has an account. The rate limit slows down
        # anyone trying to collect addresses this way.
        raise ApiError(409, "email_taken", "An account with this email already exists.") from None

    log_in(user)
    logger.info("auth.register user_id=%s", user.id)
    return jsonify(user=_user_json(user)), 201


@bp.post("/login")
@limiter.limit(limit_from_settings("rate_limit_login"))
@limiter.limit(
    limit_from_settings("rate_limit_login_account"),
    key_func=login_account,
    deduct_when=failed_login,
)
def login() -> Response:
    email, password = _read_credentials()

    db = get_session()
    user = db.scalars(select(User).where(User.email == email)).one_or_none()
    if user is None:
        spend_equal_time(password)
        logger.warning("auth.login_failed reason=unknown_email ip=%s", request.remote_addr)
        raise ApiError(401, "invalid_credentials", INVALID_CREDENTIALS)
    if not verify_password(user.password_hash, password):
        logger.warning(
            "auth.login_failed reason=wrong_password user_id=%s ip=%s",
            user.id,
            request.remote_addr,
        )
        raise ApiError(401, "invalid_credentials", INVALID_CREDENTIALS)

    # The password is known to be correct here, which is the only moment we
    # can re-hash it with stronger parameters if they have changed.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()

    log_in(user)
    logger.info("auth.login user_id=%s", user.id)
    return jsonify(user=_user_json(user))


@bp.post("/logout")
def logout() -> tuple[str, int]:
    log_out()
    return "", 204


@bp.get("/me")
@login_required
def me() -> Response:
    return jsonify(user=_user_json(current_user()))


def _read_credentials() -> tuple[str, str]:
    data: Any = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_request", "Send a JSON object with email and password.")
    email, password = data.get("email"), data.get("password")
    if not (isinstance(email, str) and isinstance(password, str) and email and password):
        raise ApiError(400, "invalid_request", "email and password are required.")
    if len(email) > MAX_EMAIL_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
        raise ApiError(400, "invalid_request", "email or password is too long.")
    return normalise_email(email), password


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _validate_new_account(email: str, password: str) -> None:
    if not _EMAIL_PATTERN.fullmatch(email):
        raise ApiError(400, "invalid_email", "Enter a valid email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError(
            400,
            "weak_password",
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )


def _user_json(user: User) -> dict[str, Any]:
    return {"id": user.id, "email": user.email}
