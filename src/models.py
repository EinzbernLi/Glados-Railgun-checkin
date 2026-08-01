from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo


BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def beijing_now() -> datetime:
    return datetime.now(BEIJING_TIMEZONE)


class CheckinState(str, Enum):
    SUCCESS = "success"
    ALREADY = "already"
    AUTH_ERROR = "auth_error"
    NETWORK_ERROR = "network_error"
    API_ERROR = "api_error"

    @property
    def successful(self) -> bool:
        return self in {self.SUCCESS, self.ALREADY}

    @property
    def label(self) -> str:
        return {
            self.SUCCESS: "签到成功",
            self.ALREADY: "今日已签到",
            self.AUTH_ERROR: "认证失败",
            self.NETWORK_ERROR: "网络失败",
            self.API_ERROR: "接口失败",
        }[self]


class ExchangeState(str, Enum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class CheckinOutcome:
    state: CheckinState
    points_added: int = 0
    message: str = ""


@dataclass
class CheckinResult:
    account_index: int
    domain: str
    checkin_state: CheckinState = CheckinState.API_ERROR
    days: int | None = None
    points_total: int | None = None
    points_added: int = 0
    exchange_state: ExchangeState = ExchangeState.SKIPPED
    exchange_message: str = "未兑换"
    points_needed: int | None = None
    diagnostic: str = ""
    error: str = ""

    @property
    def failed(self) -> bool:
        return not self.checkin_state.successful


@dataclass
class NotificationModel:
    title: str
    summary: str
    severity: str
    results: list[CheckinResult]
    generated_at: datetime = field(default_factory=beijing_now)

    @classmethod
    def from_results(cls, results: list[CheckinResult]) -> "NotificationModel":
        accounts = len({result.account_index for result in results})
        failures = sum(result.failed for result in results)
        if failures:
            return cls(
                title=f"签到汇总异常｜{failures} 项需要处理",
                summary=f"{accounts} 个签到目标 · {failures} 项异常",
                severity="error",
                results=results,
            )
        if accounts == 1:
            days = next((r.days for r in results if r.days is not None), None)
            suffix = f"剩余 {days} 天" if days is not None else "0 异常"
            title = f"签到汇总完成｜1 个签到目标 · {suffix}"
        else:
            title = f"签到汇总完成｜{accounts} 个签到目标 · 0 异常"
        return cls(
            title=title,
            summary=f"{accounts} 个签到目标 · 0 项异常",
            severity="success",
            results=results,
        )


@dataclass(frozen=True)
class RenderedMessage:
    title: str
    body: str


@dataclass(frozen=True)
class ChannelResult:
    channel: str
    success: bool
    error: str = ""
