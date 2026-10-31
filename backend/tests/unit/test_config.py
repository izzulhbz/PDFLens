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
