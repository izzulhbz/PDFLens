import pytest

from app.config import ConfigError, Settings

VALID_ENV = {
    "DATABASE_URL": "postgresql+psycopg://user:db-password-123@localhost:5433/pdflens",
    "SECRET_KEY": "k" * 40,
}


def test_reads_settings_and_normalises_values():
    settings = Settings.from_env(
        {**VALID_ENV, "LOG_LEVEL": "debug", "OLLAMA_BASE_URL": "http://ollama:11434/"}
    )

    assert settings.log_level == "DEBUG"
    assert settings.ollama_base_url == "http://ollama:11434"
    assert settings.ollama_embed_model == "nomic-embed-text"


@pytest.mark.parametrize("missing", ["DATABASE_URL", "SECRET_KEY"])
def test_missing_required_setting_fails_at_startup(missing):
    env = {k: v for k, v in VALID_ENV.items() if k != missing}

    with pytest.raises(ConfigError, match=missing):
        Settings.from_env(env)


def test_blank_required_setting_counts_as_missing():
    with pytest.raises(ConfigError, match="SECRET_KEY"):
        Settings.from_env({**VALID_ENV, "SECRET_KEY": "   "})


def test_short_secret_key_is_rejected():
    with pytest.raises(ConfigError, match="at least 32"):
        Settings.from_env({**VALID_ENV, "SECRET_KEY": "too-short"})


def test_unknown_log_level_is_rejected():
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        Settings.from_env({**VALID_ENV, "LOG_LEVEL": "LOUD"})


def test_repr_never_shows_secrets():
    settings = Settings.from_env(VALID_ENV)

    text = repr(settings)

    assert "db-password-123" not in text
    assert VALID_ENV["SECRET_KEY"] not in text


def test_security_defaults_are_strict():
    settings = Settings.from_env(VALID_ENV)

    assert settings.session_cookie_secure is True
    assert settings.cors_allowed_origins == ()
    assert settings.trusted_proxy_count == 0


@pytest.mark.parametrize(("raw", "expected"), [("false", False), ("0", False), ("TRUE", True)])
def test_boolean_settings(raw, expected):
    settings = Settings.from_env({**VALID_ENV, "SESSION_COOKIE_SECURE": raw})

    assert settings.session_cookie_secure is expected


def test_invalid_boolean_is_rejected():
    with pytest.raises(ConfigError, match="SESSION_COOKIE_SECURE"):
        Settings.from_env({**VALID_ENV, "SESSION_COOKIE_SECURE": "maybe"})


def test_cors_origins_are_parsed_from_a_comma_separated_list():
    settings = Settings.from_env(
        {**VALID_ENV, "CORS_ALLOWED_ORIGINS": "http://127.0.0.1:5173, https://app.example.com/"}
    )

    assert settings.cors_allowed_origins == ("http://127.0.0.1:5173", "https://app.example.com")


@pytest.mark.parametrize(
    "origin", ["*", "https://*.example.com", "example.com", "http://a.com/path"]
)
def test_wildcard_or_malformed_cors_origin_is_rejected(origin):
    with pytest.raises(ConfigError, match="CORS_ALLOWED_ORIGINS"):
        Settings.from_env({**VALID_ENV, "CORS_ALLOWED_ORIGINS": origin})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SESSION_LIFETIME_HOURS", "0"),
        ("SESSION_LIFETIME_HOURS", "eight"),
        ("TRUSTED_PROXY_COUNT", "-1"),
        ("RATE_LIMIT_LOGIN", "lots"),
    ],
)
def test_invalid_numbers_and_rate_limits_are_rejected(name, value):
    with pytest.raises(ConfigError, match=name):
        Settings.from_env({**VALID_ENV, name: value})
