from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import Blocked, RateLimited, RoomNotFound
from app.main import create_app


class Body(BaseModel):
    text: str


def make_client() -> TestClient:
    app: FastAPI = create_app()

    @app.get("/boom/rate-limited")
    def rate_limited() -> None:
        raise RateLimited(7)

    @app.get("/boom/blocked")
    def blocked() -> None:
        raise Blocked(datetime(2026, 10, 20, 15, 0, tzinfo=UTC))

    @app.get("/boom/room")
    def room() -> None:
        raise RoomNotFound()

    @app.post("/boom/validate")
    def validate(body: Body) -> None:
        return None

    @app.get("/boom/unexpected")
    def unexpected() -> None:
        raise RuntimeError("secret detail")

    return TestClient(app, raise_server_exceptions=False)


def test_app_error_uses_shared_format() -> None:
    response = make_client().get("/boom/rate-limited")

    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "code": "RATE_LIMITED",
            "message": "You are sending messages too fast. Try again in 7 seconds.",
            "retry_after": 7,
        }
    }


def test_blocked_includes_until() -> None:
    error = make_client().get("/boom/blocked").json()["error"]

    assert error["code"] == "BLOCKED"
    assert error["until"] == "2026-10-20T15:00:00+00:00"


def test_default_message_is_used() -> None:
    response = make_client().get("/boom/room")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROOM_NOT_FOUND"
    assert response.json()["error"]["message"]


def test_request_validation_becomes_validation_failed() -> None:
    response = make_client().post("/boom/validate", json={})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["message"].startswith("body.text")


def test_unknown_route_uses_shared_format(client: TestClient) -> None:
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unexpected_error_hides_details() -> None:
    response = make_client().get("/boom/unexpected")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret detail" not in response.text
