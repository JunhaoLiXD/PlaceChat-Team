"""CORS: fixed origins from CORS_ORIGINS, plus Vercel PR previews via CORS_ORIGIN_REGEX."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

PREVIEW_REGEX = r"^https://placechat-[a-z0-9-]+-junhaolixds-projects\.vercel\.app$"


@pytest.fixture
def preview_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("CORS_ORIGIN_REGEX", PREVIEW_REGEX)
    get_settings.cache_clear()
    yield TestClient(create_app())
    get_settings.cache_clear()


def preflight(client: TestClient, origin: str) -> str | None:
    response = client.options(
        "/api/v1/rooms",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    return response.headers.get("access-control-allow-origin")


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3000",
        "https://placechat-o604xecwi-junhaolixds-projects.vercel.app",
        "https://placechat-git-chore-preview-cors-junhaolixds-projects.vercel.app",
    ],
)
def test_allowed_origins(preview_client: TestClient, origin: str) -> None:
    assert preflight(preview_client, origin) == origin


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example.com",
        "https://placechat-abc-otherteam.vercel.app",
        "http://placechat-abc-junhaolixds-projects.vercel.app",
        "https://placechat-abc-junhaolixds-projects.vercel.app.evil.com",
    ],
)
def test_other_origins_are_rejected(preview_client: TestClient, origin: str) -> None:
    assert preflight(preview_client, origin) is None
