"""POST /api/v1/rooms/{room_id}/messages runs the §4 pipeline against an isolated SQLite database.

Steps owned by other modules (membership, blocks, rate limit, word filter) are replaced with
fakes that record their calls, so these tests check the order and the stop-at-first-failure rule.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import Session as AuthSession
from app.core.auth import get_current_session
from app.core.db import Base, get_db
from app.core.errors import Blocked, NotAMember, RateLimited, RoomNotFound
from app.main import create_app
from app.modules.messaging import service
from app.modules.messaging.models import Message
from app.modules.rooms.models import Room
from app.modules.rooms.service import Membership

SESSION_ID = str(uuid4())
Published = list[tuple[str, str, dict[str, Any]]]


class Pipeline:
    """Fakes for the other modules' steps. Set `fail[step]` to make that step raise."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: dict[str, Exception] = {}
        self.published: Published = []

    def step(self, name: str, result: Any = None) -> Callable[..., Any]:
        def fake(*args: Any) -> Any:
            self.calls.append(name)
            if name in self.fail:
                raise self.fail[name]
            return result(*args) if callable(result) else result

        return fake


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def room(db: Session) -> Room:
    now = datetime.now(UTC)
    room = Room(
        id=uuid4(),
        name="Library West",
        description="Quiet floors.",
        category="library",
        latitude=29.6513,
        longitude=-82.3429,
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(room)
    db.commit()
    return room


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch) -> Pipeline:
    pipeline = Pipeline()

    def membership(_db: Session, session_id: str, room_id: str) -> Membership:
        return Membership(room_id, session_id, "Quiet Otter", datetime.now(UTC))

    monkeypatch.setattr(service, "ensure_member", pipeline.step("ensure_member", membership))
    monkeypatch.setattr(service, "check_not_blocked", pipeline.step("check_not_blocked"))
    monkeypatch.setattr(service, "check_rate_limit", pipeline.step("check_rate_limit"))
    monkeypatch.setattr(service, "filter_text", pipeline.step("filter_text", lambda text: text))
    monkeypatch.setattr(
        service,
        "publish",
        lambda topic, event, payload: pipeline.published.append((topic, event, payload)),
    )
    return pipeline


@pytest.fixture
def client(db: Session, pipeline: Pipeline) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_session] = lambda: AuthSession(SESSION_ID, True)
    with TestClient(app) as client:
        yield client


def send(client: TestClient, room_id: UUID, body: Any) -> Any:
    return client.post(f"/api/v1/rooms/{room_id}/messages", json={"body": body})


def stored(db: Session) -> list[Message]:
    return list(db.scalars(select(Message)))


def test_send_stores_and_broadcasts(
    client: TestClient, db: Session, room: Room, pipeline: Pipeline
) -> None:
    response = send(client, room.id, "  hello <b>world</b>  ")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "room_id", "nickname", "body", "created_at"}
    assert (body["room_id"], body["nickname"]) == (str(room.id), "Quiet Otter")
    assert body["body"] == "hello <b>world</b>"  # trimmed, stored as typed

    [message] = stored(db)
    assert str(message.id) == body["id"]
    assert (message.room_id, str(message.session_id)) == (room.id, SESSION_ID)
    assert (message.nickname, message.body) == ("Quiet Otter", "hello <b>world</b>")
    assert message.removed_at is None

    assert pipeline.calls == [
        "ensure_member",
        "check_not_blocked",
        "check_rate_limit",
        "filter_text",
    ]
    assert pipeline.published == [(f"room:{room.id}", "message.created", body)]


def test_broadcast_never_includes_session_id(
    client: TestClient, room: Room, pipeline: Pipeline
) -> None:
    send(client, room.id, "hi")

    [(_, _, payload)] = pipeline.published
    assert "session_id" not in payload
    assert SESSION_ID not in str(payload)


def test_filtered_text_is_what_gets_stored(
    client: TestClient, db: Session, room: Room, pipeline: Pipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "filter_text", lambda text: text.replace("darn", "****"))

    response = send(client, room.id, "darn it")

    assert response.json()["body"] == "**** it"
    assert stored(db)[0].body == "**** it"
    assert pipeline.published[0][2]["body"] == "**** it"


@pytest.mark.parametrize(
    ("step", "error", "status", "code", "calls"),
    [
        ("ensure_member", RoomNotFound(), 404, "ROOM_NOT_FOUND", ["ensure_member"]),
        ("ensure_member", NotAMember(), 403, "NOT_A_MEMBER", ["ensure_member"]),
        (
            "check_not_blocked",
            Blocked(until=datetime(2026, 10, 21, 12, tzinfo=UTC)),
            403,
            "BLOCKED",
            ["ensure_member", "check_not_blocked"],
        ),
        (
            "check_rate_limit",
            RateLimited(retry_after=7),
            429,
            "RATE_LIMITED",
            ["ensure_member", "check_not_blocked", "check_rate_limit"],
        ),
    ],
)
def test_failing_step_stops_the_pipeline(
    client: TestClient,
    db: Session,
    room: Room,
    pipeline: Pipeline,
    step: str,
    error: Exception,
    status: int,
    code: str,
    calls: list[str],
) -> None:
    pipeline.fail[step] = error

    response = send(client, room.id, "hello")

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert pipeline.calls == calls
    assert stored(db) == []
    assert pipeline.published == []


def test_rate_limit_error_includes_retry_after(
    client: TestClient, room: Room, pipeline: Pipeline
) -> None:
    pipeline.fail["check_rate_limit"] = RateLimited(retry_after=7)

    assert send(client, room.id, "hello").json()["error"]["retry_after"] == 7


@pytest.mark.parametrize("text", ["", "   \n\t ", "a" * 501])
def test_invalid_text_is_rejected_before_the_rate_limit(
    client: TestClient, db: Session, room: Room, pipeline: Pipeline, text: str
) -> None:
    response = send(client, room.id, text)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    # Step 3 fails before step 4, so a rejected message never counts against the limit.
    assert pipeline.calls == ["ensure_member", "check_not_blocked"]
    assert stored(db) == []
    assert pipeline.published == []


@pytest.mark.parametrize("payload", [{}, {"body": 5}, {"body": "hi", "session_id": "x"}])
def test_malformed_request_is_rejected(
    client: TestClient, room: Room, pipeline: Pipeline, payload: dict[str, Any]
) -> None:
    response = client.post(f"/api/v1/rooms/{room.id}/messages", json=payload)

    assert response.status_code == 422
    assert pipeline.calls == []


def test_send_requires_a_token(room: Room) -> None:
    with TestClient(create_app()) as client:
        response = send(client, room.id, "hello")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
