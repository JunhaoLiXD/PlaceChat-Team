"""GET /api/v1/rooms/{room_id}/messages returns recent visible room history."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import Session as AuthSession
from app.core.auth import get_current_session
from app.core.db import Base, get_db
from app.main import create_app
from app.modules.messaging.models import Message
from app.modules.rooms.models import Room, RoomMember

SESSION_ID = uuid4()
OTHER_SESSION_ID = uuid4()


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
    value = Room(
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
    db.add(value)
    db.commit()
    return value


@pytest.fixture
def client(db: Session, room: Room) -> Iterator[TestClient]:
    db.add(
        RoomMember(
            room_id=room.id,
            session_id=SESSION_ID,
            nickname="Quiet Otter",
            joined_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )
    )
    db.commit()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_session] = lambda: AuthSession(str(SESSION_ID), True)
    with TestClient(app) as value:
        yield value


def add_message(db: Session, room_id: UUID, created_at: datetime, mine: bool) -> Message:
    message = Message(
        id=uuid4(),
        room_id=room_id,
        session_id=SESSION_ID if mine else OTHER_SESSION_ID,
        nickname="Quiet Otter" if mine else "Calm Fox",
        body=str(created_at),
        created_at=created_at,
    )
    db.add(message)
    return message


def test_history_returns_newest_twenty_oldest_first(
    client: TestClient, db: Session, room: Room
) -> None:
    now = datetime.now(UTC)
    db.add_all(
        [
            add_message(db, room.id, now + timedelta(seconds=index), index % 2 == 0)
            for index in range(25)
        ]
    )
    db.commit()

    response = client.get(f"/api/v1/rooms/{room.id}/messages")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 20
    assert [item["body"] for item in body] == [
        str(now + timedelta(seconds=index)) for index in range(5, 25)
    ]
    assert body[0]["is_mine"] is False
    assert body[1]["is_mine"] is True
    assert all("session_id" not in item for item in body)


def test_history_after_returns_only_newer_messages(
    client: TestClient, db: Session, room: Room
) -> None:
    now = datetime.now(UTC)
    messages = [
        add_message(db, room.id, now + timedelta(seconds=index), False) for index in range(3)
    ]
    db.commit()

    response = client.get(f"/api/v1/rooms/{room.id}/messages?after={messages[0].id}")

    assert [item["id"] for item in response.json()] == [str(messages[1].id), str(messages[2].id)]


def test_history_requires_membership(db: Session, room: Room) -> None:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_session] = lambda: AuthSession(str(SESSION_ID), True)

    with TestClient(app) as client:
        response = client.get(f"/api/v1/rooms/{room.id}/messages")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_A_MEMBER"
