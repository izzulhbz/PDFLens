"""Application settings, read from environment variables.

Every setting comes from the environment, so the same code and Docker image
run in dev, CI and Compose with different values, and no secret ever lives
in the source code. Settings are validated once at start-up: a missing or
malformed value stops the app immediately with a clear message, instead of
failing later on the first request that needs it.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from limits import parse_many

MIN_SECRET_KEY_LENGTH = 32
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


class ConfigError(Exception):
    """A required setting is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    # repr=False keeps secrets out of logs and tracebacks: printing a Settings
    # object never shows the database password or the signing key.
    database_url: str = field(repr=False)
    secret_key: str = field(repr=False)
    log_level: str = "INFO"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_embed_model: str = "nomic-embed-text"
    # How long health checks wait for Ollama before reporting it unreachable.
    ollama_health_timeout_seconds: float = 2.0
    # How long one embedding request may take. The first request after
    # Ollama starts also loads the model into memory, which is slow on a CPU.
    ollama_embed_timeout_seconds: float = 120.0

    # --- Uploads ---
    # Where uploaded PDFs are stored. Relative paths are relative to the
    # working directory (backend/ in dev mode); Docker uses a volume.
    upload_dir: str = "uploads"

    # --- Sessions ---
    # Secure cookies are only sent over HTTPS. On by default; turn it off
    # only for local development over plain http.
    session_cookie_secure: bool = True
    # After this long, a session cookie is rejected and the user logs in again.
    session_lifetime_hours: int = 8

    # --- Cross-origin requests ---
    # Browser origins (scheme://host:port) allowed to call the API from a
    # different origin. Empty means none: the React app is served from the
    # same origin as the API (Nginx in Docker, the Vite proxy in dev).
    cors_allowed_origins: tuple[str, ...] = ()
    # How many reverse proxies (Nginx) sit in front of the app. Their
    # X-Forwarded-For header is only trusted when this is above 0;
    # otherwise any client could fake its IP address and dodge rate limits.
    trusted_proxy_count: int = 0

    # --- Rate limits, in Flask-Limiter's notation ---
    # Per client IP (nobody is logged in yet):
    rate_limit_login: str = "5 per minute;30 per hour"
    rate_limit_register: str = "10 per hour"
    # Per logged-in user:
    rate_limit_upload: str = "20 per hour"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        """Build settings from environment variables (or a given mapping, in tests)."""
        env = os.environ if env is None else env

        secret_key = _required(env, "SECRET_KEY")
        if len(secret_key) < MIN_SECRET_KEY_LENGTH:
            raise ConfigError(f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters.")

        log_level = env.get("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in LOG_LEVELS:
            raise ConfigError(f"LOG_LEVEL must be one of {sorted(LOG_LEVELS)}.")

        return cls(
            database_url=_required(env, "DATABASE_URL"),
            secret_key=secret_key,
            log_level=log_level,
            ollama_base_url=env.get("OLLAMA_BASE_URL", cls.ollama_base_url).rstrip("/"),
            ollama_embed_model=env.get("OLLAMA_EMBED_MODEL", cls.ollama_embed_model),
            ollama_embed_timeout_seconds=float(
                _int(
                    env,
                    "OLLAMA_EMBED_TIMEOUT_SECONDS",
                    int(cls.ollama_embed_timeout_seconds),
                    minimum=1,
                )
            ),
            upload_dir=env.get("UPLOAD_DIR", "").strip() or cls.upload_dir,
            session_cookie_secure=_bool(env, "SESSION_COOKIE_SECURE", cls.session_cookie_secure),
            session_lifetime_hours=_int(
                env, "SESSION_LIFETIME_HOURS", cls.session_lifetime_hours, minimum=1
            ),
            cors_allowed_origins=_origins(env, "CORS_ALLOWED_ORIGINS"),
            trusted_proxy_count=_int(env, "TRUSTED_PROXY_COUNT", cls.trusted_proxy_count),
            rate_limit_login=_rate_limit(env, "RATE_LIMIT_LOGIN", cls.rate_limit_login),
            rate_limit_register=_rate_limit(env, "RATE_LIMIT_REGISTER", cls.rate_limit_register),
            rate_limit_upload=_rate_limit(env, "RATE_LIMIT_UPLOAD", cls.rate_limit_upload),
        )


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set. See .env.example.")
    return value


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name, "").strip().lower()
    if not value:
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ConfigError(f"{name} must be true or false.")


def _int(env: Mapping[str, str], name: str, default: int, minimum: int = 0) -> int:
    value = env.get(name, "").strip()
    if not value:
        return default
    try:
        number = int(value)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number.") from None
    if number < minimum:
        raise ConfigError(f"{name} must be at least {minimum}.")
    return number


def _origins(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    origins = [o.strip().rstrip("/") for o in env.get(name, "").split(",") if o.strip()]
    for origin in origins:
        parts = urlsplit(origin)
        # A wildcard would let any website make logged-in requests with the
        # user's cookie, so only exact origins are accepted.
        if (
            parts.scheme not in ("http", "https")
            or not parts.netloc
            or "*" in origin
            or parts.path
            or parts.query
        ):
            raise ConfigError(
                f"{name}: {origin!r} is not an origin like https://app.example.com:8080."
            )
    return tuple(origins)


def _rate_limit(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name, "").strip() or default
    try:
        parse_many(value)
    except ValueError:
        raise ConfigError(f"{name}: {value!r} is not a rate limit like '5 per minute'.") from None
    return value
