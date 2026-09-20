"""Unit tests for environment-based configuration defaults and overrides."""
from app import config


def test_defaults_when_env_vars_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("TOOLS_API_KEY", raising=False)
    settings = config.get_settings()
    monkeypatch.delenv("OPERATOR_API_KEY", raising=False)
    monkeypatch.delenv("IDENTITY_ISOLATION", raising=False)
    monkeypatch.delenv("IDENTITY_REBINDING", raising=False)
    assert settings.database_path == "./app/data/db/mock.db"
    assert settings.tools_api_key == "change-me"


def test_isolation_is_enforced_and_rebinding_denied_unless_asked_otherwise(monkeypatch):
    monkeypatch.delenv("IDENTITY_ISOLATION", raising=False)
    monkeypatch.delenv("IDENTITY_REBINDING", raising=False)
    settings = config.get_settings()
    assert settings.identity_isolation == "enforced"
    assert settings.isolation_enforced is True
    assert settings.identity_rebinding == "denied"
    assert settings.rebinding_allowed is False


def test_only_the_exact_spelling_turns_isolation_off(monkeypatch):
    monkeypatch.setenv("IDENTITY_ISOLATION", "disabled")
    assert config.get_settings().isolation_enforced is False
    for typo in ("Disabled", "off", "false", ""):
        monkeypatch.setenv("IDENTITY_ISOLATION", typo)
        assert config.get_settings().isolation_enforced is True


def test_only_the_exact_spelling_allows_rebinding(monkeypatch):
    monkeypatch.setenv("IDENTITY_REBINDING", "allowed")
    assert config.get_settings().rebinding_allowed is True
    monkeypatch.setenv("IDENTITY_REBINDING", "Allowed")
    assert config.get_settings().rebinding_allowed is False


def test_the_operator_key_has_its_own_default(monkeypatch):
    monkeypatch.delenv("OPERATOR_API_KEY", raising=False)
    monkeypatch.setenv("TOOLS_API_KEY", "agent-key")
    settings = config.get_settings()
    assert settings.operator_api_key == "change-me-operator"
    assert settings.operator_api_key != settings.tools_api_key


def test_reads_values_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", "/tmp/custom.db")
    monkeypatch.setenv("TOOLS_API_KEY", "secret-key")
    settings = config.get_settings()
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-key")
    settings = config.get_settings()
    assert settings.database_path == "/tmp/custom.db"
    assert settings.tools_api_key == "secret-key"
    assert settings.operator_api_key == "operator-key"
