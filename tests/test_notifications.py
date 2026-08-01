from datetime import datetime, timezone

from src.models import (
    CheckinResult,
    CheckinState,
    ExchangeState,
    NotificationModel,
)
from src.push import NotificationDispatcher, PushDeerAdapter, PushPlusAdapter
from src.renderers import (
    MarkdownRenderer,
    PushPlusRenderer,
    TelegramRenderer,
    TextRenderer,
)


def model_with(state=CheckinState.ALREADY):
    result = CheckinResult(
        account_index=1,
        domain="glados.cloud",
        checkin_state=state,
        days=120,
        points_total=72,
        points_added=0,
        exchange_state=ExchangeState.SKIPPED,
        points_needed=28,
    )
    return NotificationModel.from_results([result])


def test_today_already_checked_is_rendered_as_normal():
    model = model_with()
    assert "签到汇总完成" in model.title
    assert "今日已签到" in TextRenderer().render(model).body
    assert "异常" not in model.title


def test_renderers_escape_channel_markup():
    model = model_with()
    model.results[0].error = "<bad>&"
    html = PushPlusRenderer().render(model).body
    telegram = TelegramRenderer().render(model)[0].body
    assert "<bad>" not in html
    assert "<bad>" not in telegram


def test_all_renderer_families_preserve_semantics():
    model = model_with()
    outputs = [
        TextRenderer().render(model).body,
        MarkdownRenderer().render(model).body,
        PushPlusRenderer().render(model).body,
        TelegramRenderer().render(model)[0].body,
    ]
    for output in outputs:
        assert "签到目标 1" in output
        assert "今日已签到" in output
        assert "glados.cloud" in output
        assert "还差 28 分" in output
        assert "北京时间" in output


def test_utc_timestamp_is_rendered_as_beijing_time():
    model = model_with()
    model.generated_at = datetime(2026, 8, 1, 6, 26, tzinfo=timezone.utc)
    outputs = [
        TextRenderer().render(model).body,
        MarkdownRenderer().render(model).body,
        PushPlusRenderer().render(model).body,
        TelegramRenderer().render(model)[0].body,
    ]
    assert all("2026-08-01 14:26（北京时间）" in output for output in outputs)


def test_default_generated_timestamp_is_timezone_aware_beijing_time():
    generated_at = model_with().generated_at
    assert generated_at.utcoffset() is not None
    assert getattr(generated_at.tzinfo, "key", None) == "Asia/Shanghai"


def test_multiple_domains_share_one_notification_model():
    model = model_with()
    model.results.append(
        CheckinResult(
            account_index=2,
            domain="railgun.info",
            checkin_state=CheckinState.ALREADY,
            days=90,
            points_total=20,
            exchange_state=ExchangeState.SKIPPED,
            points_needed=80,
        )
    )
    model = NotificationModel.from_results(model.results)
    pushplus = PushPlusRenderer().render(model).body
    pushdeer = MarkdownRenderer().render(model).body
    telegram = TelegramRenderer().render(model)
    assert "glados.cloud" in pushplus and "railgun.info" in pushplus
    assert "glados.cloud" in pushdeer and "railgun.info" in pushdeer
    assert len(telegram) == 1
    assert "glados.cloud" in telegram[0].body
    assert "railgun.info" in telegram[0].body


def test_aggregated_notification_shows_each_domain_actual_policy():
    results = [
        CheckinResult(
            account_index=1,
            domain="glados.cloud",
            exchange_plan="plan100",
            exchange_enabled=True,
            checkin_state=CheckinState.ALREADY,
            points_total=70,
            points_needed=30,
            exchange_message="未兑换 · 还差 30 分",
        ),
        CheckinResult(
            account_index=2,
            domain="railgun.info",
            exchange_plan="plan500",
            exchange_enabled=False,
            checkin_state=CheckinState.ALREADY,
            points_total=70,
            exchange_message="兑换已关闭",
        ),
    ]
    model = NotificationModel.from_results(results)
    outputs = [
        TextRenderer().render(model).body,
        MarkdownRenderer().render(model).body,
        PushPlusRenderer().render(model).body,
        TelegramRenderer().render(model)[0].body,
    ]
    for output in outputs:
        assert "plan100（启用）" in output
        assert "plan500（关闭）" in output


class SuccessfulPushResponse:
    status_code = 200
    content = b"json"

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_pushplus_and_pushdeer_each_send_one_aggregated_card():
    model = model_with()
    model.results.append(
        CheckinResult(
            account_index=2,
            domain="railgun.info",
            checkin_state=CheckinState.ALREADY,
            points_total=20,
        )
    )
    model = NotificationModel.from_results(model.results)
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        payload = {"code": 200} if "pushplus" in url else {"code": 0}
        return SuccessfulPushResponse(payload)

    PushPlusAdapter("fake-token", post).send(model)
    PushDeerAdapter("fake-sendkey", post).send(model)

    assert len(calls) == 2
    assert "glados.cloud" in calls[0][1]["content"]
    assert "railgun.info" in calls[0][1]["content"]
    assert "glados.cloud" in calls[1][1]["desp"]
    assert "railgun.info" in calls[1][1]["desp"]


def test_telegram_splits_only_when_aggregated_content_is_too_long():
    results = [
        CheckinResult(
            account_index=index,
            domain=f"service-{index}.example.com",
            checkin_state=CheckinState.ALREADY,
            points_total=index,
        )
        for index in range(1, 100)
    ]
    messages = TelegramRenderer().render(NotificationModel.from_results(results))
    assert len(messages) > 1
    assert all(len(message.body) <= TelegramRenderer.max_length for message in messages)
    combined = "\n".join(message.body for message in messages)
    assert "service-1.example.com" in combined
    assert "service-99.example.com" in combined


class Adapter:
    def __init__(self, name, succeeds, calls):
        self.name = name
        self.succeeds = succeeds
        self.calls = calls

    def send(self, model):
        self.calls.append(self.name)
        if not self.succeeds:
            raise RuntimeError("fake send failure")


def test_dispatcher_attempts_every_channel_and_requires_all_success():
    calls = []
    adapters = [
        Adapter("pushdeer", True, calls),
        Adapter("pushplus", False, calls),
        Adapter("telegram", True, calls),
    ]
    results = NotificationDispatcher(adapters).send(model_with())
    assert calls == ["pushdeer", "pushplus", "telegram"]
    assert [result.success for result in results] == [True, False, True]
    assert not all(result.success for result in results)


def test_no_channels_is_explicit_skip():
    assert NotificationDispatcher([]).send(model_with()) == []
