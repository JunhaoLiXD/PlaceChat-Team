from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import realtime
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def no_real_broadcasts(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A developer's backend/.env may hold staging keys; tests must never broadcast for real."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"test tried to call Realtime: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(refuse))
    monkeypatch.setattr(realtime, "get_http_client", lambda: client)
    yield
    client.close()
