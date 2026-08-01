import pytest

from src.config import AppConfig
from src.exceptions import ConfigError


def base_env(**overrides):
    env = {"GLADOS_COOKIES": "fake-cookie-a"}
    env.update(overrides)
    return env


def test_glados_cookies_bind_only_to_glados_domain():
    config = AppConfig.from_env(base_env(GLADOS_COOKIES=" fake-a & & fake-b "))
    assert config.cookies == ("fake-a", "fake-b")
    assert config.domains == ("glados.cloud",)
    assert [(target.domain, target.cookie) for target in config.targets] == [
        ("glados.cloud", "fake-a"),
        ("glados.cloud", "fake-b"),
    ]


@pytest.mark.parametrize("value", [None, "", "  ", "&&"])
def test_missing_or_empty_cookie_is_config_error(value):
    env = {} if value is None else {"GLADOS_COOKIES": value}
    with pytest.raises(ConfigError):
        AppConfig.from_env(env)


def test_railgun_cookie_can_be_used_without_glados_cookie():
    config = AppConfig.from_env({"RAILGUN_COOKIES": "railgun-a&railgun-b"})
    assert [(target.domain, target.cookie) for target in config.targets] == [
        ("railgun.info", "railgun-a"),
        ("railgun.info", "railgun-b"),
    ]


def test_builtin_cookie_groups_never_cross_domains():
    config = AppConfig.from_env(
        {"GLADOS_COOKIES": "glados-a", "RAILGUN_COOKIES": "railgun-a"}
    )
    assert [(target.domain, target.cookie) for target in config.targets] == [
        ("glados.cloud", "glados-a"),
        ("railgun.info", "railgun-a"),
    ]


def test_builtin_services_bind_independent_exchange_policies():
    config = AppConfig.from_env(
        {
            "GLADOS_COOKIES": "glados-a",
            "RAILGUN_COOKIES": "railgun-a",
            "GLADOS_EXCHANGE_PLAN": "plan100",
            "GLADOS_ENABLE_EXCHANGE": "true",
            "RAILGUN_EXCHANGE_PLAN": "plan500",
            "RAILGUN_ENABLE_EXCHANGE": "false",
        }
    )
    assert [
        (target.domain, target.exchange_plan, target.enable_exchange)
        for target in config.targets
    ] == [
        ("glados.cloud", "plan100", True),
        ("railgun.info", "plan500", False),
    ]


def test_railgun_policy_inherits_glados_policy_when_unset_or_empty():
    overrides = (
        {},
        {"RAILGUN_EXCHANGE_PLAN": "", "RAILGUN_ENABLE_EXCHANGE": ""},
    )
    for railgun_overrides in overrides:
        config = AppConfig.from_env(
            {
                "RAILGUN_COOKIES": "railgun-a",
                "GLADOS_EXCHANGE_PLAN": "plan200",
                "GLADOS_ENABLE_EXCHANGE": "false",
                **railgun_overrides,
            }
        )
        target = config.targets[0]
        assert (target.exchange_plan, target.enable_exchange) == ("plan200", False)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("GLADOS_EXCHANGE_PLAN", "plan999"),
        ("RAILGUN_EXCHANGE_PLAN", "plan999"),
        ("RAILGUN_ENABLE_EXCHANGE", "sometimes"),
    ],
)
def test_rejects_invalid_builtin_exchange_policy(name, value):
    with pytest.raises(ConfigError, match=name):
        AppConfig.from_env(
            {
                "RAILGUN_COOKIES": "railgun-a",
                name: value,
            }
        )


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


def test_custom_domain_json_creates_explicit_targets():
    config = AppConfig.from_env(
        {
            "CUSTOM_DOMAIN_COOKIES": (
                '{"check.example.com":["custom-a","custom-b"]}'
            ),
            "GLADOS_ALLOW_CUSTOM_DOMAINS": "true",
        }
    )
    assert [(target.domain, target.cookie) for target in config.targets] == [
        ("check.example.com", "custom-a"),
        ("check.example.com", "custom-b"),
    ]


def test_custom_domain_object_binds_its_own_policy_to_every_cookie():
    config = AppConfig.from_env(
        {
            "CUSTOM_DOMAIN_COOKIES": (
                '{"check.example.com":{"cookies":["custom-a","custom-b"],'
                '"exchange_plan":"plan200","enable_exchange":false}}'
            ),
            "GLADOS_ALLOW_CUSTOM_DOMAINS": "true",
            "GLADOS_EXCHANGE_PLAN": "plan100",
            "GLADOS_ENABLE_EXCHANGE": "true",
        }
    )
    assert [
        (target.cookie, target.exchange_plan, target.enable_exchange)
        for target in config.targets
    ] == [
        ("custom-a", "plan200", False),
        ("custom-b", "plan200", False),
    ]


def test_custom_domain_legacy_list_inherits_glados_policy():
    config = AppConfig.from_env(
        {
            "CUSTOM_DOMAIN_COOKIES": '{"check.example.com":["custom-a"]}',
            "GLADOS_ALLOW_CUSTOM_DOMAINS": "true",
            "GLADOS_EXCHANGE_PLAN": "plan100",
            "GLADOS_ENABLE_EXCHANGE": "false",
        }
    )
    target = config.targets[0]
    assert (target.exchange_plan, target.enable_exchange) == ("plan100", False)


@pytest.mark.parametrize(
    "mapping",
    [
        "not-json",
        "[]",
        "{}",
        '{"check.example.com":[]}',
        '{"check.example.com":[""]}',
        '{"glados.cloud":["duplicate"]}',
        '{"check.example.com":{}}',
        '{"check.example.com":{"cookies":["safe"],"exchange_plan":"bad"}}',
        '{"check.example.com":{"cookies":["safe"],"enable_exchange":"false"}}',
        '{"check.example.com":{"cookies":["safe"],"enable_exchagne":false}}',
    ],
)
def test_rejects_invalid_custom_domain_mappings(mapping):
    with pytest.raises(ConfigError):
        AppConfig.from_env(
            {
                "CUSTOM_DOMAIN_COOKIES": mapping,
                "GLADOS_ALLOW_CUSTOM_DOMAINS": "true",
            }
        )


def test_custom_domain_json_requires_explicit_opt_in():
    with pytest.raises(ConfigError):
        AppConfig.from_env(
            {"CUSTOM_DOMAIN_COOKIES": '{"check.example.com":["custom-a"]}'}
        )


def test_legacy_multi_domain_configuration_is_rejected_as_ambiguous():
    with pytest.raises(ConfigError, match="映射不明确"):
        AppConfig.from_env(
            base_env(GLADOS_DOMAINS="glados.cloud,railgun.info")
        )


def test_legacy_single_railgun_domain_remains_compatible():
    config = AppConfig.from_env(base_env(GLADOS_DOMAINS="railgun.info"))
    assert [(target.domain, target.cookie) for target in config.targets] == [
        ("railgun.info", "fake-cookie-a")
    ]


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


def test_summary_counts_targets_and_unique_domains():
    config = AppConfig.from_env(
        {
            "GLADOS_COOKIES": "glados-a&glados-b",
            "RAILGUN_COOKIES": "railgun-a",
        }
    )
    summary = config.safe_summary()
    assert summary["accounts"] == 3
    assert summary["domains"] == ("glados.cloud", "railgun.info")


def test_summary_lists_each_target_policy_without_credentials():
    config = AppConfig.from_env(
        {
            "GLADOS_COOKIES": "private-glados",
            "RAILGUN_COOKIES": "private-railgun",
            "GLADOS_EXCHANGE_PLAN": "plan100",
            "RAILGUN_EXCHANGE_PLAN": "plan500",
            "RAILGUN_ENABLE_EXCHANGE": "false",
        }
    )
    summary = config.safe_summary()
    assert summary["target_policies"] == (
        {
            "domain": "glados.cloud",
            "accounts": 1,
            "exchange_enabled": True,
            "exchange_plan": "plan100",
            "exchange_threshold": 100,
            "exchange_days": 10,
        },
        {
            "domain": "railgun.info",
            "accounts": 1,
            "exchange_enabled": False,
            "exchange_plan": "plan500",
            "exchange_threshold": 500,
            "exchange_days": 100,
        },
    )
    assert "private-glados" not in repr(summary)
    assert "private-railgun" not in repr(summary)


def test_custom_policy_error_never_echoes_cookie():
    cookie = "private-cookie-must-not-appear"
    with pytest.raises(ConfigError) as caught:
        AppConfig.from_env(
            {
                "CUSTOM_DOMAIN_COOKIES": (
                    '{"check.example.com":{"cookies":["'
                    + cookie
                    + '"],"exchange_plan":"bad"}}'
                ),
                "GLADOS_ALLOW_CUSTOM_DOMAINS": "true",
            }
        )
    assert cookie not in str(caught.value)
