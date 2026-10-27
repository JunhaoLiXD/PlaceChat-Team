"""Exercise the public route, service, and real query against an isolated test database."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.db import Base, get_db
from app.main import create_app
from app.modules.rooms import service
from app.modules.rooms.models import Room, RoomMember


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


@pytest.mark.parametrize(
    "age,left,expected",
    [
        (0, False, 1),
        (29.999999, False, 1),
        (30, False, 1),
        (30.000001, False, 0),
        (60, False, 0),
        (120, False, 0),
        (0, True, 0),
    ],
)
def test_public_counts_use_inclusive_presence_boundary(
    rooms_client: TestClient,
    rooms_db: Session,
    monkeypatch: pytest.MonkeyPatch,
    age: float,
    left: bool,
    expected: int,
) -> None:
    now = datetime(2026, 10, 22, 12, tzinfo=UTC)
    monkeypatch.setattr(service, "utc_now", lambda: now)
    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None))
    room = add_room(rooms_db, "Test Library")
    rooms_db.add(
        RoomMember(
            room_id=room.id,
            session_id=uuid4(),
            nickname="Quiet Otter",
            joined_at=now - timedelta(minutes=5),
            last_seen_at=now - timedelta(seconds=age),
            left_at=now if left else None,
        )
    )
    rooms_db.commit()
    response = rooms_client.get("/api/v1/rooms")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["participant_count"] == expected


def test_counts_are_per_room_and_keep_empty_rooms(
    rooms_client: TestClient, rooms_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 10, 22, 12, tzinfo=UTC)
    monkeypatch.setattr(service, "utc_now", lambda: now)
    # Presence configuration must be independent of the 60-second nickname hold.
    monkeypatch.setattr(
        service, "get_settings", lambda: Settings(_env_file=None, presence_timeout_seconds=10)
    )
    same_user = uuid4()
    for name, ages, left, status in [
        ("A Empty", [], False, "active"),
        ("B Present", [0, 10, 10.000001], False, "active"),
        ("C Timed out", [11, 30, 60], False, "active"),
        ("D Left", [0], True, "active"),
        ("E Other", [0], False, "active"),
        ("F Archived", [0], False, "archived"),
    ]:
        room = add_room(rooms_db, name, status)
        for index, age in enumerate(ages):
            rooms_db.add(
                RoomMember(
                    room_id=room.id,
                    session_id=same_user if index == 0 else uuid4(),
                    nickname=f"Quiet Otter {index}",
                    joined_at=now - timedelta(minutes=5),
                    last_seen_at=now - timedelta(seconds=age),
                    left_at=now if left else None,
                )
            )
        rooms_db.commit()
    response = rooms_client.get("/api/v1/rooms")
    assert response.status_code == 200
    assert [(room["name"], room["participant_count"]) for room in response.json()] == [
        ("A Empty", 0),
        ("B Present", 2),
        ("C Timed out", 0),
        ("D Left", 0),
        ("E Other", 1),
    ]
