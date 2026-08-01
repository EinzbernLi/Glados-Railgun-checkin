from __future__ import annotations

from collections import defaultdict
from html import escape

from .models import NotificationModel, RenderedMessage


def _group(model: NotificationModel):
    grouped = defaultdict(list)
    for result in model.results:
        grouped[result.account_index].append(result)
    return grouped


def _exchange_text(result) -> str:
    if result.points_needed is not None and result.exchange_state.value == "skipped":
        return f"未兑换 · 还差 {result.points_needed} 分"
    return result.exchange_message


class TextRenderer:
    def render(self, model: NotificationModel) -> RenderedMessage:
        lines = [model.summary, ""]
        for account, results in _group(model).items():
            lines.append(f"账号 {account}")
            for result in results:
                days = f"{result.days} 天" if result.days is not None else "未知"
                points = (
                    str(result.points_total)
                    if result.points_total is not None
                    else "未知"
                )
                lines.append(
                    f"{result.domain}  {result.checkin_state.label} · 剩余 {days} · "
                    f"积分 {points}（本次 +{result.points_added}）"
                )
                lines.append(f"兑换  {_exchange_text(result)}")
                if result.error:
                    lines.append(f"错误  {result.error}")
            lines.append("")
        lines.append(f"运行时间  {model.generated_at:%Y-%m-%d %H:%M}")
        return RenderedMessage(model.title, "\n".join(lines).strip())


class MarkdownRenderer:
    def render(self, model: NotificationModel) -> RenderedMessage:
        lines = [f"## {model.title}", model.summary]
        for account, results in _group(model).items():
            lines.extend(["", f"### 账号 {account}"])
            for result in results:
                lines.append(
                    f"- **{result.domain}**：{result.checkin_state.label}；"
                    f"{_exchange_text(result)}"
                )
        return RenderedMessage(model.title, "\n".join(lines))


class PushPlusRenderer:
    def render(self, model: NotificationModel) -> RenderedMessage:
        parts = [
            f"<h2>{escape(model.title)}</h2>",
            f"<p>{escape(model.summary)}</p>",
        ]
        for account, results in _group(model).items():
            parts.append(f"<h3>账号 {account}</h3>")
            for result in results:
                days = f"{result.days} 天" if result.days is not None else "未知"
                points = (
                    str(result.points_total)
                    if result.points_total is not None
                    else "未知"
                )
                parts.append(
                    "<p>"
                    f"<strong>{escape(result.domain)}</strong><br>"
                    f"状态　{escape(result.checkin_state.label)}<br>"
                    f"剩余　{escape(days)}<br>"
                    f"积分　{escape(points)}（本次 +{result.points_added}）<br>"
                    f"兑换　{escape(_exchange_text(result))}"
                    + (f"<br>错误　{escape(result.error)}" if result.error else "")
                    + "</p>"
                )
        parts.append(f"<p>运行时间　{model.generated_at:%Y-%m-%d %H:%M}</p>")
        return RenderedMessage(model.title, "".join(parts))


class TelegramRenderer:
    max_length = 3900

    def render(self, model: NotificationModel) -> list[RenderedMessage]:
        header = f"<b>{escape(model.title)}</b>\n{escape(model.summary)}"
        blocks = []
        for account, results in _group(model).items():
            lines = [f"<b>账号 {account}</b>"]
            for result in results:
                lines.append(
                    f"{escape(result.domain)}　{escape(result.checkin_state.label)}"
                )
                if result.days is not None:
                    lines.append(f"剩余　{result.days} 天")
                if result.points_total is not None:
                    lines.append(
                        f"积分　{result.points_total}（本次 +{result.points_added}）"
                    )
                lines.append(f"兑换　{escape(_exchange_text(result))}")
                if result.error:
                    lines.append(f"错误　{escape(result.error)}")
            blocks.append("\n".join(lines))

        messages = []
        current = header
        for block in blocks:
            candidate = f"{current}\n\n{block}"
            if len(candidate) > self.max_length and current != header:
                messages.append(RenderedMessage(model.title, current))
                current = f"{header}\n\n{block}"
            else:
                current = candidate
        messages.append(RenderedMessage(model.title, current))
        return messages
