"""POST /api/v1/messages/{message_id}/reports stores anonymous message reports."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import Session as AuthSession
from app.core.auth import get_current_session
from app.core.db import Base, get_db
from app.main import create_app
from app.modules.messaging.models import Message
from app.modules.rooms.models import Room
from app.modules.safety.models import Report

REPORTER_ID = uuid4()
AUTHOR_ID = uuid4()


def new_room() -> Room:
    now = datetime.now(UTC)
    return Room(
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


def new_message(room: Room, session_id: UUID = AUTHOR_ID) -> Message:
    return Message(
        id=uuid4(),
        room_id=room.id,
        session_id=session_id,
        nickname="Calm Fox",
        body="Please help.",
        created_at=datetime.now(UTC),
    )


def setup_client(db: Session, session_id: UUID = REPORTER_ID) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_session] = lambda: AuthSession(str(session_id), True)
    return TestClient(app)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_report_stores_message_room_reason_and_time(db: Session) -> None:
    room = new_room()
    message = new_message(room)
    db.add_all([room, message])
    db.commit()

    with setup_client(db) as client:
        response = client.post(
            f"/api/v1/messages/{message.id}/reports", json={"reason": "harassment"}
        )

    assert response.status_code == 201
    body = response.json()
    assert body["message_id"] == str(message.id)
    assert body["room_id"] == str(room.id)
    assert body["reason"] == "harassment"
    assert body["status"] == "pending"
    assert "reporter_session_id" not in body
    [report] = list(db.scalars(select(Report)))
    assert report.reporter_session_id == REPORTER_ID


def test_report_rejects_own_message(db: Session) -> None:
    room = new_room()
    message = new_message(room, REPORTER_ID)
    db.add_all([room, message])
    db.commit()

    with setup_client(db) as client:
        response = client.post(f"/api/v1/messages/{message.id}/reports", json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CANNOT_REPORT_OWN"


def test_report_rejects_second_report(db: Session) -> None:
    room = new_room()
    message = new_message(room)
    db.add_all([room, message])
    db.commit()

    with setup_client(db) as client:
        first = client.post(f"/api/v1/messages/{message.id}/reports", json={})
        second = client.post(f"/api/v1/messages/{message.id}/reports", json={})

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ALREADY_REPORTED"


def test_report_rejects_unknown_or_removed_message(db: Session) -> None:
    room = new_room()
    message = new_message(room)
    removed = new_message(room)
    removed.removed_at = datetime.now(UTC)
    db.add_all([room, message, removed])
    db.commit()

    with setup_client(db) as client:
        unknown = client.post(f"/api/v1/messages/{uuid4()}/reports", json={})
        hidden = client.post(f"/api/v1/messages/{removed.id}/reports", json={})

    assert unknown.status_code == 404
    assert hidden.status_code == 404
    assert unknown.json()["error"]["code"] == "MESSAGE_NOT_FOUND"
    assert hidden.json()["error"]["code"] == "MESSAGE_NOT_FOUND"


def test_report_requires_a_token(db: Session) -> None:
    with setup_client(db) as client:
        client.app.dependency_overrides.pop(get_current_session)
        response = client.post(f"/api/v1/messages/{uuid4()}/reports", json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
