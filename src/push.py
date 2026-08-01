from __future__ import annotations

from collections.abc import Callable

import requests

from .config import AppConfig
from .constants import PUSHDEER_URL, PUSHPLUS_URL, TELEGRAM_URL_TEMPLATE
from .exceptions import PushError
from .models import ChannelResult, NotificationModel
from .renderers import MarkdownRenderer, PushPlusRenderer, TelegramRenderer


class PushDeerAdapter:
    name = "pushdeer"

    def __init__(self, sendkey: str, post: Callable = requests.post):
        self.sendkey = sendkey
        self.post = post

    def send(self, model: NotificationModel):
        rendered = MarkdownRenderer().render(model)
        response = self.post(
            PUSHDEER_URL,
            json={
                "pushkey": self.sendkey,
                "text": rendered.title,
                "desp": rendered.body,
                "type": "markdown",
            },
            timeout=10,
        )
        _require_success(response, "PushDeer")


class PushPlusAdapter:
    name = "pushplus"

    def __init__(self, token: str, post: Callable = requests.post):
        self.token = token
        self.post = post

    def send(self, model: NotificationModel):
        rendered = PushPlusRenderer().render(model)
        response = self.post(
            PUSHPLUS_URL,
            json={
                "token": self.token,
                "title": rendered.title,
                "content": rendered.body,
                "template": "html",
            },
            timeout=10,
        )
        payload = _require_json(response, "PushPlus")
        if response.status_code >= 400 or payload.get("code") != 200:
            raise PushError("PushPlus 返回失败状态")


class TelegramAdapter:
    name = "telegram"

    def __init__(
        self, token: str, chat_id: str, post: Callable = requests.post
    ):
        self.url = TELEGRAM_URL_TEMPLATE.format(token=token)
        self.chat_id = chat_id
        self.post = post

    def send(self, model: NotificationModel):
        for rendered in TelegramRenderer().render(model):
            response = self.post(
                self.url,
                json={
                    "chat_id": self.chat_id,
                    "text": rendered.body,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            payload = _require_json(response, "Telegram")
            if response.status_code >= 400 or payload.get("ok") is not True:
                raise PushError("Telegram 返回失败状态")


class NotificationDispatcher:
    def __init__(self, adapters):
        self.adapters = list(adapters)

    def send(self, model: NotificationModel) -> list[ChannelResult]:
        results = []
        for adapter in self.adapters:
            try:
                adapter.send(model)
                results.append(ChannelResult(adapter.name, True))
            except Exception:
                results.append(ChannelResult(adapter.name, False, "发送失败"))
        return results


def build_adapters(config: AppConfig, post: Callable = requests.post):
    registry = []
    if config.pushdeer_sendkey:
        registry.append(PushDeerAdapter(config.pushdeer_sendkey, post))
    if config.pushplus_token:
        registry.append(PushPlusAdapter(config.pushplus_token, post))
    if config.tg_bot_token and config.tg_chat_id:
        registry.append(
            TelegramAdapter(config.tg_bot_token, config.tg_chat_id, post)
        )
    return registry


def _require_json(response, channel: str) -> dict:
    try:
        payload = response.json()
    except (ValueError, TypeError) as exc:
        raise PushError(f"{channel} 返回非 JSON 内容") from exc
    if not isinstance(payload, dict):
        raise PushError(f"{channel} 返回无效 JSON")
    return payload


def _require_success(response, channel: str):
    if response.status_code >= 400:
        raise PushError(f"{channel} 返回 HTTP 失败")
    if getattr(response, "content", b""):
        payload = _require_json(response, channel)
        if payload.get("code") not in (None, 0):
            raise PushError(f"{channel} 返回业务失败")
