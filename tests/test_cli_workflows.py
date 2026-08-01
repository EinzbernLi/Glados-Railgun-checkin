from pathlib import Path
import re

import yaml

from src.models import CheckinOutcome, CheckinState
from src.main import main


ROOT = Path(__file__).resolve().parents[1]


def test_dry_run_uses_fake_values_and_makes_no_network(capsys):
    env = {
        "GLADOS_COOKIES": "fake-cookie-a&fake-cookie-b",
        "PUSHPLUS_TOKEN": "fake-token",
    }

    def forbidden_factory(*_):
        raise AssertionError("dry-run must not construct an API")

    assert main(["--dry-run"], environ=env, api_factory=forbidden_factory) == 0
    output = capsys.readouterr().out
    assert "账号数: 2" in output
    assert "pushplus" in output
    assert "fake-cookie" not in output
    assert "fake-token" not in output


def test_config_error_returns_two_without_constructing_api():
    def forbidden_factory(*_):
        raise AssertionError("config error must stop before API construction")

    assert main([], environ={}, api_factory=forbidden_factory) == 2


class SuccessfulAPI:
    def status(self):
        return 120

    def checkin(self):
        return CheckinOutcome(CheckinState.ALREADY)

    def points(self):
        return 72

    def exchange(self, _plan):
        raise AssertionError("72 points must not trigger plan500 exchange")

    def close(self):
        pass


class FakePostResponse:
    def __init__(self, payload, status_code=200, content=b"json"):
        self.payload = payload
        self.status_code = status_code
        self.content = content

    def json(self):
        return self.payload


def test_partial_notification_failure_attempts_all_and_returns_one(capsys, caplog):
    calls = []

    def post(url, **_kwargs):
        calls.append(url)
        if "pushplus" in url:
            return FakePostResponse({"code": 500})
        return FakePostResponse({"code": 0})

    env = {
        "GLADOS_COOKIES": "fake-cookie",
        "PUSHDEER_SENDKEY": "fake-sendkey",
        "PUSHPLUS_TOKEN": "fake-token",
    }
    code = main(
        [],
        environ=env,
        api_factory=lambda *_: SuccessfulAPI(),
        post=post,
    )
    assert code == 1
    assert len(calls) == 2
    assert "pushdeer" in calls[0]
    assert "pushplus" in calls[1]
    output = capsys.readouterr().out + capsys.readouterr().err + caplog.text
    assert "fake-cookie" not in output
    assert "fake-sendkey" not in output
    assert "fake-token" not in output


def test_success_without_notification_returns_zero():
    assert (
        main(
            [],
            environ={"GLADOS_COOKIES": "fake-cookie"},
            api_factory=lambda *_: SuccessfulAPI(),
        )
        == 0
    )


def load_workflow(name):
    with (ROOT / ".github" / "workflows" / name).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def test_workflow_yaml_is_parseable_and_split():
    assert load_workflow("ci.yml")
    assert load_workflow("gladosCheck.yml")


def test_ci_does_not_reference_secrets():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "secrets." not in text
    assert "pytest" in text


def test_scheduled_workflow_has_safe_triggers_and_cron():
    path = ROOT / ".github" / "workflows" / "gladosCheck.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    triggers = workflow[True]  # YAML 1.1 parses the key `on` as True.
    assert "push" not in triggers
    assert triggers["schedule"] == [{"cron": "0 4,10 * * *"}]
    assert "workflow_dispatch" in triggers
    assert "pytest" not in text
    assert "matrix:" not in text
    assert "pip install --upgrade pip" not in text
    assert "keepalive" not in text.lower()
    assert "delete-workflow-runs" not in text
    assert "continue-on-error" not in text
    assert "contents: read" in text
    assert "timeout-minutes: 3" in text


def test_all_actions_are_pinned_to_commit_sha():
    for name in ("ci.yml", "gladosCheck.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        uses = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", text)
        assert uses
        assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in uses)
