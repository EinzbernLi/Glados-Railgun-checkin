import pytest

from src.config import AppConfig
from src.exceptions import ConfigError


def base_env(**overrides):
    env = {"GLADOS_COOKIES": "fake-cookie-a"}
    env.update(overrides)
    return env


def test_parses_multiple_accounts_and_default_domains():
    config = AppConfig.from_env(base_env(GLADOS_COOKIES=" fake-a & & fake-b "))
    assert config.cookies == ("fake-a", "fake-b")
    assert config.domains == ("glados.cloud", "railgun.info")


@pytest.mark.parametrize("value", [None, "", "  ", "&&"])
def test_missing_or_empty_cookie_is_config_error(value):
    env = {} if value is None else {"GLADOS_COOKIES": value}
    with pytest.raises(ConfigError):
        AppConfig.from_env(env)


@pytest.mark.parametrize(
    "domain",
    [
        "https://evil.example",
        "evil.example/path",
        "user@evil.example",
        "127.0.0.1",
        "evil.example:443",
        "-evil.example",
    ],
)
def test_rejects_unsafe_domains(domain):
    with pytest.raises(ConfigError):
        AppConfig.from_env(
            base_env(
                GLADOS_DOMAINS=domain,
                GLADOS_ALLOW_CUSTOM_DOMAINS="true",
            )
        )


def test_custom_domain_requires_explicit_opt_in():
    with pytest.raises(ConfigError):
        AppConfig.from_env(base_env(GLADOS_DOMAINS="check.example.com"))

    config = AppConfig.from_env(
        base_env(
            GLADOS_DOMAINS="check.example.com",
            GLADOS_ALLOW_CUSTOM_DOMAINS="true",
        )
    )
    assert config.domains == ("check.example.com",)


@pytest.mark.parametrize(
    "env",
    [
        {"TG_BOT_TOKEN": "fake-token"},
        {"TG_CHAT_ID": "fake-chat"},
    ],
)
def test_telegram_requires_complete_pair(env):
    with pytest.raises(ConfigError):
        AppConfig.from_env(base_env(**env))


def test_legacy_notification_secrets_auto_enable_channels():
    config = AppConfig.from_env(
        base_env(
            PUSHDEER_SENDKEY="fake-sendkey",
            PUSHPLUS_TOKEN="fake-token",
            TG_BOT_TOKEN="fake-bot",
            TG_CHAT_ID="fake-chat",
        )
    )
    assert config.enabled_channels == ("pushdeer", "pushplus", "telegram")


def test_no_notification_secret_is_valid():
    assert AppConfig.from_env(base_env()).enabled_channels == ()


def test_numeric_limits_are_validated():
    with pytest.raises(ConfigError):
        AppConfig.from_env(base_env(GLADOS_RETRY_MAX="8"))
    with pytest.raises(ConfigError):
        AppConfig.from_env(base_env(GLADOS_RETRY_BACKOFF="-1"))


def test_summary_never_contains_secrets():
    env = base_env(
        GLADOS_COOKIES="fake-cookie-never-print",
        PUSHPLUS_TOKEN="fake-token-never-print",
    )
    summary = AppConfig.from_env(env).safe_summary()
    assert summary["accounts"] == 1
    text = repr(summary)
    assert "fake-cookie-never-print" not in text
    assert "fake-token-never-print" not in text

