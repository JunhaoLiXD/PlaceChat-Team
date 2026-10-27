"""publish() sends one REST broadcast per event and never raises (§4, §6.5)."""

import json
import logging
from collections.abc import Callable

import httpx
import pytest

from app.core import realtime
from app.core.config import Settings

SECRET = "sb_secret_test_value"
Handler = Callable[[httpx.Request], httpx.Response]


def use_settings(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    settings = Settings(_env_file=None, **values)
    monkeypatch.setattr(realtime, "get_settings", lambda: settings)


def use_transport(monkeypatch: pytest.MonkeyPatch, handler: Handler) -> list[httpx.Request]:
    sent: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    monkeypatch.setattr(realtime, "get_http_client", lambda: client)
    return sent


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(monkeypatch, supabase_url="https://ref.supabase.co/", supabase_secret_key=SECRET)


@pytest.mark.usefixtures("configured")
def test_publish_posts_to_private_broadcast_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = use_transport(monkeypatch, lambda _: httpx.Response(202))

    realtime.publish("room:abc", "message.created", {"id": "m1", "body": "hi"})

    [request] = sent
    assert request.method == "POST"
    assert str(request.url) == (
        "https://ref.supabase.co/realtime/v1/api/broadcast/room%3Aabc/events/message.created"
        "?private=true"
    )
    assert request.headers["apikey"] == SECRET
    assert json.loads(request.content) == {"id": "m1", "body": "hi"}


def network_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


@pytest.mark.usefixtures("configured")
@pytest.mark.parametrize(
    "handler",
    [lambda _: httpx.Response(500), network_down],
    ids=["server-error", "network-error"],
)
def test_publish_logs_failures_without_raising(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, handler: Handler
) -> None:
    use_transport(monkeypatch, handler)

    with caplog.at_level(logging.ERROR):
        realtime.publish("rooms", "room.changed", {"room_id": "r1"})

    assert "Realtime publish failed for rooms room.changed" in caplog.text
    assert SECRET not in caplog.text


def test_publish_without_settings_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    use_settings(monkeypatch)
    sent = use_transport(monkeypatch, lambda _: httpx.Response(202))

    with caplog.at_level(logging.WARNING):
        realtime.publish("rooms", "room.changed", {"room_id": "r1"})

    assert sent == []
    assert "Realtime is not configured" in caplog.text
