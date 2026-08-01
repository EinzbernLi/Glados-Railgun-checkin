from __future__ import annotations

from collections.abc import Callable

from .config import AppConfig, CheckinTarget
from .constants import EXCHANGE_PLANS
from .exceptions import (
    ApiRejectedError,
    AuthenticationError,
    NetworkError,
    ProtocolError,
)
from .models import CheckinResult, CheckinState, ExchangeState


HANDLED_ERRORS = (AuthenticationError, NetworkError, ProtocolError, ApiRejectedError)


class Checker:
    def __init__(self, config: AppConfig, api_factory: Callable):
        self.config = config
        self.api_factory = api_factory

    def run(self) -> list[CheckinResult]:
        results = []
        for account_index, target in enumerate(self.config.targets, 1):
            results.append(self._run_one(account_index, target))
        return results

    def _run_one(self, account_index: int, target: CheckinTarget) -> CheckinResult:
        result = CheckinResult(
            account_index=account_index,
            domain=target.domain,
            exchange_plan=target.exchange_plan,
            exchange_enabled=target.enable_exchange,
        )
        api = self.api_factory(target.domain, target.cookie)
        try:
            try:
                result.days = api.status()
            except HANDLED_ERRORS as exc:
                result.diagnostic = _safe_error(exc)

            try:
                outcome = api.checkin()
                result.checkin_state = outcome.state
                result.points_added = outcome.points_added
            except AuthenticationError as exc:
                result.checkin_state = CheckinState.AUTH_ERROR
                result.error = _safe_error(exc)
            except NetworkError as exc:
                result.checkin_state = CheckinState.NETWORK_ERROR
                result.error = _safe_error(exc)
            except (ProtocolError, ApiRejectedError) as exc:
                result.checkin_state = CheckinState.API_ERROR
                result.error = _safe_error(exc)

            try:
                result.points_total = api.points()
            except HANDLED_ERRORS as exc:
                if not result.diagnostic:
                    result.diagnostic = _safe_error(exc)

            self._exchange_if_eligible(api, result, target)
            return result
        finally:
            api.close()

    def _exchange_if_eligible(
        self, api, result: CheckinResult, target: CheckinTarget
    ) -> None:
        threshold, days = EXCHANGE_PLANS[target.exchange_plan]
        if not target.enable_exchange:
            result.exchange_message = "兑换已关闭"
            return
        if result.points_total is None:
            result.exchange_message = "积分未知，未兑换"
            return
        if result.points_total < threshold:
            result.points_needed = threshold - result.points_total
            result.exchange_message = f"未兑换 · 还差 {result.points_needed} 分"
            return
        try:
            api.exchange(target.exchange_plan)
            result.exchange_state = ExchangeState.SUCCESS
            result.exchange_message = f"已兑换 {days} 天 · 消耗 {threshold} 分"
        except HANDLED_ERRORS as exc:
            result.exchange_state = ExchangeState.FAILED
            result.exchange_message = "兑换失败"
            result.diagnostic = _safe_error(exc)


def _safe_error(exc: Exception) -> str:
    return str(exc)[:200]
