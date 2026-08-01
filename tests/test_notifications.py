from src.models import (
    CheckinResult,
    CheckinState,
    ExchangeState,
    NotificationModel,
)
from src.push import NotificationDispatcher
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
    assert "签到完成" in model.title
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
        assert "账号 1" in output
        assert "今日已签到" in output
        assert "glados.cloud" in output
        assert "还差 28 分" in output


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
