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

MIN_SECRET_KEY_LENGTH = 32
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


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
        )


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set. See .env.example.")
    return value
