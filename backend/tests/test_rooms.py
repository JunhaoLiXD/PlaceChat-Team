"""Exercise the public route, service, and real query against an isolated test database."""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.main import create_app
from app.modules.rooms.models import Base, Room


@pytest.fixture
def rooms_db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


@pytest.fixture
def rooms_client(rooms_db: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: rooms_db
    with TestClient(app) as client:
        yield client


def add_room(db: Session, name: str, status: str = "active") -> Room:
    now = datetime.now(UTC)
    room = Room(
        id=uuid4(),
        name=name,
        description="Test room description",
        category="library",
        latitude=29.65,
        longitude=-82.34,
        status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(room)
    db.commit()
    return room


def test_public_rooms_response_fields(rooms_client: TestClient, rooms_db: Session) -> None:
    room = add_room(rooms_db, "Test Library")
    response = rooms_client.get("/api/v1/rooms")
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(room.id),
            "name": room.name,
            "description": room.description,
            "category": "library",
            "latitude": 29.65,
            "longitude": -82.34,
            "participant_count": 0,
        }
    ]


def test_empty_rooms(rooms_client: TestClient) -> None:
    response = rooms_client.get("/api/v1/rooms")
    assert response.status_code == 200
    assert response.json() == []


def test_archived_rooms_excluded(rooms_client: TestClient, rooms_db: Session) -> None:
    add_room(rooms_db, "Archived Library", "archived")
    add_room(rooms_db, "Active Library")
    assert [room["name"] for room in rooms_client.get("/api/v1/rooms").json()] == ["Active Library"]


def test_only_archived_rooms_returns_empty(rooms_client: TestClient, rooms_db: Session) -> None:
    add_room(rooms_db, "Archived Library", "archived")
    assert rooms_client.get("/api/v1/rooms").json() == []


def test_rooms_sorted_by_name(rooms_client: TestClient, rooms_db: Session) -> None:
    for name in ["Z Test Library", "A Test Library", "M Test Library"]:
        add_room(rooms_db, name)
    response = rooms_client.get("/api/v1/rooms")
    assert [room["name"] for room in response.json()] == [
        "A Test Library",
        "M Test Library",
        "Z Test Library",
    ]


def test_database_failure_hides_details(rooms_db: Session) -> None:
    app = create_app()

    def unavailable_db() -> None:
        raise RuntimeError("private database connection details")

    app.dependency_overrides[get_db] = unavailable_db
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/rooms")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private database" not in response.text
