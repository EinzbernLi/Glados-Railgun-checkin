from dataclasses import dataclass

from src.checker import Checker
from src.config import AppConfig
from src.exceptions import NetworkError
from src.models import CheckinOutcome, CheckinState, ExchangeState


@dataclass
class Scenario:
    status_error: bool = False
    checkin_state: CheckinState = CheckinState.SUCCESS
    points: int | None = 50
    exchange_error: bool = False


class FakeAPI:
    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = []

    def status(self):
        self.calls.append("status")
        if self.scenario.status_error:
            raise NetworkError("status timeout")
        return 120

    def checkin(self):
        self.calls.append("checkin")
        return CheckinOutcome(self.scenario.checkin_state, points_added=1)

    def points(self):
        self.calls.append("points")
        if self.scenario.points is None:
            raise NetworkError("points timeout")
        return self.scenario.points

    def exchange(self, plan):
        self.calls.append("exchange")
        if self.scenario.exchange_error:
            raise NetworkError("exchange timeout")
        return "兑换成功"

    def close(self):
        self.calls.append("close")


def make_config(**values):
    env = {
        "GLADOS_COOKIES": values.pop("cookies", "fake-a"),
        "GLADOS_DOMAINS": values.pop("domains", "glados.cloud"),
        "GLADOS_ENABLE_EXCHANGE": values.pop("exchange", "true"),
        "GLADOS_EXCHANGE_PLAN": values.pop("plan", "plan100"),
    }
    env.update(values)
    return AppConfig.from_env(env)


def test_status_failure_still_attempts_checkin_and_points():
    api = FakeAPI(Scenario(status_error=True))
    result = Checker(make_config(), lambda *_: api).run()[0]
    assert api.calls[:3] == ["status", "checkin", "points"]
    assert result.checkin_state is CheckinState.SUCCESS
    assert result.days is None


def test_points_below_threshold_skips_exchange():
    api = FakeAPI(Scenario(points=99))
    result = Checker(make_config(), lambda *_: api).run()[0]
    assert "exchange" not in api.calls
    assert result.exchange_state is ExchangeState.SKIPPED
    assert result.points_needed == 1


def test_points_at_threshold_executes_exchange():
    api = FakeAPI(Scenario(points=100))
    result = Checker(make_config(), lambda *_: api).run()[0]
    assert "exchange" in api.calls
    assert result.exchange_state is ExchangeState.SUCCESS


def test_failed_points_query_never_exchanges():
    api = FakeAPI(Scenario(points=None))
    result = Checker(make_config(), lambda *_: api).run()[0]
    assert "exchange" not in api.calls
    assert result.exchange_state is ExchangeState.SKIPPED


def test_all_explicit_targets_continue_after_failure_without_cross_product():
    scenarios = iter(
        [
            Scenario(checkin_state=CheckinState.NETWORK_ERROR),
            Scenario(checkin_state=CheckinState.SUCCESS),
            Scenario(checkin_state=CheckinState.ALREADY),
            Scenario(checkin_state=CheckinState.AUTH_ERROR),
        ]
    )
    apis = []

    factory_calls = []

    def factory(domain, cookie):
        factory_calls.append((domain, cookie))
        api = FakeAPI(next(scenarios))
        apis.append(api)
        return api

    config = make_config(
        cookies="glados-a&glados-b",
        domains="",
        RAILGUN_COOKIES="railgun-a&railgun-b",
    )
    results = Checker(config, factory).run()
    assert len(results) == 4
    assert factory_calls == [
        ("glados.cloud", "glados-a"),
        ("glados.cloud", "glados-b"),
        ("railgun.info", "railgun-a"),
        ("railgun.info", "railgun-b"),
    ]
    assert [result.checkin_state for result in results] == [
        CheckinState.NETWORK_ERROR,
        CheckinState.SUCCESS,
        CheckinState.ALREADY,
        CheckinState.AUTH_ERROR,
    ]
    assert all("close" in api.calls for api in apis)
