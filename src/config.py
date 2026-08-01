from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Mapping

from .constants import DEFAULT_DOMAINS, EXCHANGE_PLANS
from .exceptions import ConfigError


_HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


def _bool(value: str | None, default: bool, name: str) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ConfigError(f"{name} 必须是 true/false")


def _bounded_int(value: str | None, default: int, name: str, low: int, high: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是整数") from exc
    if not low <= parsed <= high:
        raise ConfigError(f"{name} 必须在 {low}..{high} 范围内")
    return parsed


def _bounded_float(
    value: str | None, default: float, name: str, low: float, high: float
) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是数字") from exc
    if not low <= parsed <= high:
        raise ConfigError(f"{name} 必须在 {low}..{high} 范围内")
    return parsed


def _valid_hostname(host: str) -> bool:
    if any(mark in host for mark in ("://", "/", "\\", "@", ":")):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return bool(_HOST_RE.fullmatch(host))


@dataclass(frozen=True)
class AppConfig:
    cookies: tuple[str, ...]
    domains: tuple[str, ...]
    exchange_plan: str
    enable_exchange: bool
    verbose: bool
    retry_max: int
    retry_backoff: float
    connect_timeout: float
    read_timeout: float
    pushdeer_sendkey: str = ""
    pushplus_token: str = ""
    tg_bot_token: str = ""
    tg_chat_id: str = ""

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "AppConfig":
        cookies = tuple(
            item.strip()
            for item in (environ.get("GLADOS_COOKIES") or "").split("&")
            if item.strip()
        )
        if not cookies:
            raise ConfigError("GLADOS_COOKIES 缺少有效账号")

        domains = tuple(
            item.strip().lower()
            for item in (
                environ.get("GLADOS_DOMAINS") or ",".join(DEFAULT_DOMAINS)
            ).split(",")
            if item.strip()
        )
        if not domains:
            raise ConfigError("GLADOS_DOMAINS 不能为空")
        if any(not _valid_hostname(domain) for domain in domains):
            raise ConfigError("GLADOS_DOMAINS 只能包含纯 DNS 主机名")
        custom = any(domain not in DEFAULT_DOMAINS for domain in domains)
        allow_custom = _bool(
            environ.get("GLADOS_ALLOW_CUSTOM_DOMAINS"),
            False,
            "GLADOS_ALLOW_CUSTOM_DOMAINS",
        )
        if custom and not allow_custom:
            raise ConfigError("自定义域名需要 GLADOS_ALLOW_CUSTOM_DOMAINS=true")

        plan = (environ.get("GLADOS_EXCHANGE_PLAN") or "plan500").strip()
        if plan not in EXCHANGE_PLANS:
            raise ConfigError("GLADOS_EXCHANGE_PLAN 必须是 plan100/plan200/plan500")

        pushdeer = (environ.get("PUSHDEER_SENDKEY") or "").strip()
        pushplus = (environ.get("PUSHPLUS_TOKEN") or "").strip()
        tg_token = (environ.get("TG_BOT_TOKEN") or "").strip()
        tg_chat = (environ.get("TG_CHAT_ID") or "").strip()
        if bool(tg_token) != bool(tg_chat):
            raise ConfigError("TG_BOT_TOKEN 与 TG_CHAT_ID 必须同时配置")

        return cls(
            cookies=cookies,
            domains=domains,
            exchange_plan=plan,
            enable_exchange=_bool(
                environ.get("GLADOS_ENABLE_EXCHANGE"),
                True,
                "GLADOS_ENABLE_EXCHANGE",
            ),
            verbose=_bool(environ.get("GLADOS_VERBOSE"), False, "GLADOS_VERBOSE"),
            retry_max=_bounded_int(
                environ.get("GLADOS_RETRY_MAX"), 2, "GLADOS_RETRY_MAX", 0, 5
            ),
            retry_backoff=_bounded_float(
                environ.get("GLADOS_RETRY_BACKOFF"),
                0.5,
                "GLADOS_RETRY_BACKOFF",
                0,
                10,
            ),
            connect_timeout=_bounded_float(
                environ.get("GLADOS_CONNECT_TIMEOUT"),
                5,
                "GLADOS_CONNECT_TIMEOUT",
                1,
                30,
            ),
            read_timeout=_bounded_float(
                environ.get("GLADOS_READ_TIMEOUT"),
                15,
                "GLADOS_READ_TIMEOUT",
                1,
                60,
            ),
            pushdeer_sendkey=pushdeer,
            pushplus_token=pushplus,
            tg_bot_token=tg_token,
            tg_chat_id=tg_chat,
        )

    @property
    def enabled_channels(self) -> tuple[str, ...]:
        channels = []
        if self.pushdeer_sendkey:
            channels.append("pushdeer")
        if self.pushplus_token:
            channels.append("pushplus")
        if self.tg_bot_token and self.tg_chat_id:
            channels.append("telegram")
        return tuple(channels)

    def safe_summary(self) -> dict[str, object]:
        threshold, days = EXCHANGE_PLANS[self.exchange_plan]
        return {
            "accounts": len(self.cookies),
            "domains": self.domains,
            "exchange_enabled": self.enable_exchange,
            "exchange_plan": self.exchange_plan,
            "exchange_threshold": threshold,
            "exchange_days": days,
            "channels": self.enabled_channels,
            "retry_attempts": self.retry_max + 1,
        }
