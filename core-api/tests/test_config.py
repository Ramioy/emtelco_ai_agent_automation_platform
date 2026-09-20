"""Unit tests for environment-based configuration defaults and overrides."""
from app import config


def test_defaults_when_env_vars_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("TOOLS_API_KEY", raising=False)
    settings = config.get_settings()
    assert settings.database_path == "./app/data/mock.db"
    assert settings.tools_api_key == "change-me"


def test_reads_values_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", "/tmp/custom.db")
    monkeypatch.setenv("TOOLS_API_KEY", "secret-key")
    settings = config.get_settings()
    assert settings.database_path == "/tmp/custom.db"
    assert settings.tools_api_key == "secret-key"
