from __future__ import annotations

import argparse
import os
from collections.abc import Mapping

import requests

from .api import GladosAPI, HttpClient
from .checker import Checker
from .config import AppConfig
from .exceptions import ConfigError
from .logging_config import configure_logging
from .models import NotificationModel
from .push import NotificationDispatcher, build_adapters
from .renderers import TextRenderer


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    api_factory=None,
    post=requests.post,
) -> int:
    parser = argparse.ArgumentParser(description="GLaDOS / Railgun 签到")
    parser.add_argument(
        "--dry-run", action="store_true", help="只验证配置，不执行任何网络请求"
    )
    args = parser.parse_args(argv)
    source_env = os.environ if environ is None else environ

    try:
        config = AppConfig.from_env(source_env)
    except ConfigError as exc:
        print(f"配置错误: {exc}")
        return 2

    if args.dry_run:
        summary = config.safe_summary()
        print("配置验证通过（未执行网络请求）")
        print(f"账号数: {summary['accounts']}")
        print(f"域名: {', '.join(summary['domains'])}")
        print(
            f"兑换: {'启用' if summary['exchange_enabled'] else '关闭'} · "
            f"{summary['exchange_plan']}"
        )
        print(f"通知渠道: {', '.join(summary['channels']) or '未配置'}")
        print(f"HTTP 最大尝试次数: {summary['retry_attempts']}")
        return 0

    logger = configure_logging(config.verbose)
    factory = api_factory or _default_api_factory(config)
    results = Checker(config, factory).run()
    model = NotificationModel.from_results(results)
    rendered = TextRenderer().render(model)
    logger.info("%s\n%s", rendered.title, rendered.body)

    channel_results = NotificationDispatcher(build_adapters(config, post)).send(model)
    if not channel_results:
        logger.info("未配置通知渠道，跳过通知")
    else:
        for channel in channel_results:
            logger.info(
                "通知渠道 %s: %s",
                channel.channel,
                "成功" if channel.success else "失败",
            )

    checkin_failed = any(result.failed for result in results)
    notification_failed = any(not result.success for result in channel_results)
    return 1 if checkin_failed or notification_failed else 0


def _default_api_factory(config: AppConfig):
    def factory(domain: str, cookie: str):
        client = HttpClient(
            requests.Session(),
            config.retry_max,
            config.retry_backoff,
            timeout=(config.connect_timeout, config.read_timeout),
        )
        return GladosAPI(domain, cookie, client)

    return factory
