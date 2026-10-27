"""Admin room routes against an isolated SQLite database, with the admin check overridden."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import admin_rooms
from app.core.auth import Admin, require_admin
from app.core.db import Base, get_db
from app.core.errors import Forbidden, Unauthenticated
from app.main import create_app
from app.modules.rooms import admin_repository, admin_service
from app.modules.rooms.models import Room

NEW_ROOM = {
    "name": "Newell Hall",
    "description": "Open study space that never closes.",
    "category": "academic",
    "latitude": 29.6491,
    "longitude": -82.3452,
}

Published = list[tuple[str, str, dict[str, Any]]]


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
def published(monkeypatch: pytest.MonkeyPatch) -> Published:
    events: Published = []
    monkeypatch.setattr(
        admin_service,
        "publish",
        lambda topic, event, payload: events.append((topic, event, payload)),
    )
    return events


@pytest.fixture
def app(db: Session, published: Published) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: Admin(user_id="admin-1")
    return app


@pytest.fixture
def admin(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def add_room(db: Session, name: str = "Library West", status: str = "active") -> Room:
    now = datetime.now(UTC)
    room = Room(
        id=uuid4(),
        name=name,
        description="Quiet floors.",
        category="library",
        latitude=29.6513,
        longitude=-82.3429,
        status=status,
        created_at=now,
        updated_at=now,
    )
    db.add(room)
    db.commit()
    return room


def public_names(client: TestClient) -> list[str]:
    return [room["name"] for room in client.get("/api/v1/rooms").json()]


def assert_validation_failed(response: Any, text: str = "") -> None:
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert text in response.json()["error"]["message"]


# Create


def test_create_room(admin: TestClient, published: Published) -> None:
    response = admin.post("/api/v1/admin/rooms", json=NEW_ROOM)

    assert response.status_code == 201
    body = response.json()
    assert {key: body[key] for key in NEW_ROOM} == NEW_ROOM
    assert body["status"] == "active"
    assert body["created_at"] and body["updated_at"]
    assert published == [("rooms", "room.changed", {"room_id": body["id"]})]
    assert public_names(admin) == ["Newell Hall"]


def test_create_room_trims_text(admin: TestClient) -> None:
    payload = {**NEW_ROOM, "name": "  Newell Hall  ", "description": " Open late. "}
    body = admin.post("/api/v1/admin/rooms", json=payload).json()
    assert (body["name"], body["description"]) == ("Newell Hall", "Open late.")


@pytest.mark.parametrize(
    "change",
    [
        {"name": "   "},
        {"description": ""},
        {"category": "parking"},
        {"latitude": 91},
        {"longitude": -181},
        {"latitude": None},
        {"extra": "field"},
    ],
)
def test_create_room_rejects_invalid_input(
    admin: TestClient, published: Published, change: dict[str, Any]
) -> None:
    assert_validation_failed(admin.post("/api/v1/admin/rooms", json={**NEW_ROOM, **change}))
    assert published == []


@pytest.mark.parametrize("missing", ["name", "description", "category", "latitude", "longitude"])
def test_create_room_requires_every_field(admin: TestClient, missing: str) -> None:
    payload = {key: value for key, value in NEW_ROOM.items() if key != missing}
    assert_validation_failed(admin.post("/api/v1/admin/rooms", json=payload), missing)


@pytest.mark.parametrize("status", ["active", "archived"])
def test_create_room_rejects_taken_name_in_any_case(
    admin: TestClient, db: Session, published: Published, status: str
) -> None:
    add_room(db, "Library West", status)
    response = admin.post("/api/v1/admin/rooms", json={**NEW_ROOM, "name": "library WEST"})
    assert_validation_failed(response, "already exists")
    assert published == []


def test_create_room_lost_name_race(
    admin: TestClient, db: Session, published: Published, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_room(db, "Newell Hall")
    answers = iter([False, True])  # The pre-check misses a room created a moment later.
    monkeypatch.setattr(admin_repository, "name_taken", lambda *args: next(answers))

    assert_validation_failed(admin.post("/api/v1/admin/rooms", json=NEW_ROOM), "already exists")
    assert published == []


# Edit


def test_update_room_changes_only_sent_fields(
    admin: TestClient, db: Session, published: Published
) -> None:
    room = add_room(db)
    response = admin.patch(
        f"/api/v1/admin/rooms/{room.id}", json={"description": "Now open until 2 a.m."}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "Now open until 2 a.m."
    assert (body["name"], body["category"], body["latitude"]) == (
        "Library West",
        "library",
        29.6513,
    )
    assert published == [("rooms", "room.changed", {"room_id": str(room.id)})]


def test_update_room_every_field(admin: TestClient, db: Session) -> None:
    room = add_room(db)
    body = admin.patch(f"/api/v1/admin/rooms/{room.id}", json=NEW_ROOM).json()
    assert {key: body[key] for key in NEW_ROOM} == NEW_ROOM
    assert public_names(admin) == ["Newell Hall"]


def test_update_room_may_keep_its_own_name(admin: TestClient, db: Session) -> None:
    room = add_room(db, "Library West")
    response = admin.patch(f"/api/v1/admin/rooms/{room.id}", json={"name": "Library west"})
    assert response.status_code == 200
    assert response.json()["name"] == "Library west"


def test_update_room_rejects_another_rooms_name(
    admin: TestClient, db: Session, published: Published
) -> None:
    add_room(db, "Marston Science Library")
    room = add_room(db, "Library West")
    response = admin.patch(
        f"/api/v1/admin/rooms/{room.id}", json={"name": "Marston Science Library"}
    )
    assert_validation_failed(response, "already exists")
    assert published == []


@pytest.mark.parametrize(
    ("payload", "text"),
    [
        ({}, "at least one field"),
        ({"name": None}, "name cannot be null"),
        ({"status": "archived"}, "status"),
        ({"category": "parking"}, "category"),
    ],
)
def test_update_room_rejects_invalid_input(
    admin: TestClient, db: Session, payload: dict[str, Any], text: str
) -> None:
    room = add_room(db)
    assert_validation_failed(admin.patch(f"/api/v1/admin/rooms/{room.id}", json=payload), text)


# Archive


def test_archive_room(admin: TestClient, db: Session, published: Published) -> None:
    room = add_room(db)
    add_room(db, "Marston Science Library")

    response = admin.post(f"/api/v1/admin/rooms/{room.id}/archive")

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    assert public_names(admin) == ["Marston Science Library"]
    assert published == [
        ("rooms", "room.changed", {"room_id": str(room.id)}),
        (f"room:{room.id}", "room.archived", {"room_id": str(room.id)}),
    ]


# Missing or archived rooms


@pytest.mark.parametrize("status", [None, "archived"])
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [("patch", "", {"name": "Anything"}), ("post", "/archive", None)],
)
def test_missing_or_archived_room_not_found(
    admin: TestClient,
    db: Session,
    published: Published,
    status: str | None,
    method: str,
    path: str,
    payload: dict[str, str] | None,
) -> None:
    room_id = add_room(db, status=status).id if status else uuid4()
    response = admin.request(method, f"/api/v1/admin/rooms/{room_id}{path}", json=payload)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROOM_NOT_FOUND"
    assert published == []


# Only administrators


ADMIN_REQUESTS = [
    ("post", "/api/v1/admin/rooms", NEW_ROOM),
    ("patch", f"/api/v1/admin/rooms/{uuid4()}", {"name": "Anything"}),
    ("post", f"/api/v1/admin/rooms/{uuid4()}/archive", None),
]


def test_every_admin_route_requires_admin(app: FastAPI) -> None:
    admin_paths = [path for path in app.openapi()["paths"] if path.startswith("/api/v1/admin")]
    assert sorted(admin_paths) == [
        "/api/v1/admin/rooms",
        "/api/v1/admin/rooms/{room_id}",
        "/api/v1/admin/rooms/{room_id}/archive",
    ]
    routes = [route for route in admin_rooms.router.routes if isinstance(route, APIRoute)]
    assert len(routes) == 3
    for route in routes:
        assert require_admin in [dependency.call for dependency in route.dependant.dependencies]


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (Unauthenticated, 401, "UNAUTHENTICATED"),
        (Forbidden, 403, "FORBIDDEN"),
    ],
)
@pytest.mark.parametrize(("method", "path", "payload"), ADMIN_REQUESTS)
def test_non_admins_are_rejected(
    app: FastAPI,
    db: Session,
    published: Published,
    error: type[Exception],
    status: int,
    code: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
) -> None:
    def reject() -> Admin:
        raise error()

    app.dependency_overrides[require_admin] = reject
    with TestClient(app) as client:
        response = client.request(method, path, json=payload)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert db.query(Room).count() == 0
    assert published == []
