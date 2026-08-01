import json

import pytest
import requests

from src.api import GladosAPI, HttpClient
from src.exceptions import ApiRejectedError, AuthenticationError, ProtocolError
from src.models import CheckinState


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, events):
        self.events = list(events)
        self.calls = []
        self.closed = False

    def request(self, **kwargs):
        self.calls.append(kwargs)
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        return event

    def close(self):
        self.closed = True


def test_retries_429_using_retry_after_then_succeeds():
    session = FakeSession(
        [
            FakeResponse(429, {"message": "slow"}, {"Retry-After": "2"}),
            FakeResponse(200, {"code": 0}),
        ]
    )
    sleeps = []
    client = HttpClient(session, retry_max=1, retry_backoff=0.1, sleep=sleeps.append)
    response = client.request("POST", "https://glados.cloud/api/user/checkin")
    assert response.status_code == 200
    assert len(session.calls) == 2
    assert sleeps == [2.0]


@pytest.mark.parametrize("status", [401, 403, 404])
def test_regular_4xx_is_not_retried(status):
    session = FakeSession([FakeResponse(status, {"message": "denied"})])
    client = HttpClient(session, retry_max=3, retry_backoff=0, sleep=lambda _: None)
    with pytest.raises(AuthenticationError if status in (401, 403) else ProtocolError):
        client.request("GET", "https://glados.cloud/api/user/status")
    assert len(session.calls) == 1


def test_retries_timeout_exactly_to_configured_limit():
    session = FakeSession(
        [
            requests.Timeout("first"),
            requests.Timeout("second"),
            FakeResponse(200, {"code": 0}),
        ]
    )
    client = HttpClient(session, retry_max=2, retry_backoff=0, sleep=lambda _: None)
    assert client.request("GET", "https://glados.cloud/api/user/status").status_code == 200
    assert len(session.calls) == 3


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_retries_each_transient_server_status(status):
    session = FakeSession(
        [FakeResponse(status, {"message": "temporary"}), FakeResponse(200, {"code": 0})]
    )
    client = HttpClient(session, retry_max=1, retry_backoff=0, sleep=lambda _: None)
    assert client.request("GET", "https://glados.cloud/api/user/status").status_code == 200
    assert len(session.calls) == 2


def test_client_context_closes_session():
    session = FakeSession([FakeResponse(200, {"code": 0})])
    with HttpClient(session, retry_max=0, retry_backoff=0) as client:
        client.request("GET", "https://glados.cloud/api/user/status")
    assert session.closed


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"code": 0, "points": 1, "message": "ok"}, CheckinState.SUCCESS),
        ({"code": 1, "message": "checked"}, CheckinState.ALREADY),
    ],
)
def test_checkin_business_codes(payload, expected):
    client = HttpClient(FakeSession([FakeResponse(200, payload)]), 0, 0)
    outcome = GladosAPI("glados.cloud", "fake-cookie", client).checkin()
    assert outcome.state is expected


def test_invalid_json_is_protocol_error():
    client = HttpClient(
        FakeSession([FakeResponse(200, ValueError("bad json"), text="not-json")]),
        0,
        0,
    )
    with pytest.raises(ProtocolError):
        GladosAPI("glados.cloud", "fake-cookie", client).status()


def test_missing_status_field_is_protocol_error():
    client = HttpClient(FakeSession([FakeResponse(200, {"code": 0})]), 0, 0)
    with pytest.raises(ProtocolError):
        GladosAPI("glados.cloud", "fake-cookie", client).status()


def test_unknown_checkin_business_code_is_rejected():
    client = HttpClient(
        FakeSession([FakeResponse(200, {"code": 999, "message": "unknown"})]),
        0,
        0,
    )
    with pytest.raises(ApiRejectedError):
        GladosAPI("glados.cloud", "fake-cookie", client).checkin()
