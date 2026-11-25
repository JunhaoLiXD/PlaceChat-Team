"""Admin report review routes."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import Admin, require_admin
from app.core.db import Base, get_db
from app.core.errors import Forbidden, Unauthenticated
from app.main import create_app
from app.modules.messaging.models import Message
from app.modules.rooms.models import Room
from app.modules.safety.models import Report

ADMIN_ID = uuid4()
REPORTER_ID = uuid4()
OTHER_REPORTER_ID = uuid4()


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
def app(db: Session) -> Any:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: Admin(user_id=str(ADMIN_ID))
    return app


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as value:
        yield value


def add_report(
    db: Session, *, reporter_id: UUID = REPORTER_ID, room_name: str = "Library West"
) -> Report:
    now = datetime.now(UTC)
    room = Room(
        id=uuid4(),
        name=room_name,
        description="Quiet floors.",
        category="library",
        latitude=29.6513,
        longitude=-82.3429,
        status="active",
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=uuid4(),
        room_id=room.id,
        session_id=uuid4(),
        nickname="Calm Fox",
        body="Please help.",
        created_at=now,
    )
    report = Report(
        id=uuid4(),
        message_id=message.id,
        room_id=room.id,
        reporter_session_id=reporter_id,
        reason="harassment",
        status="pending",
        created_at=now,
    )
    db.add_all([room, message, report])
    db.commit()
    return report


def test_admin_lists_pending_reports_with_message_and_room(client: TestClient, db: Session) -> None:
    report = add_report(db)
    handled = add_report(db, reporter_id=OTHER_REPORTER_ID, room_name="Marston Science Library")
    handled.status = "dismissed"
    db.commit()

    response = client.get("/api/v1/admin/reports?status=pending")

    assert response.status_code == 200
    assert len(response.json()) == 1
    body = response.json()[0]
    assert body["id"] == str(report.id)
    assert body["message"]["body"] == "Please help."
    assert body["room"]["name"] == "Library West"
    assert body["status"] == "pending"


def test_remove_message_resolves_all_pending_reports_and_publishes(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = add_report(db)
    second = Report(
        id=uuid4(),
        message_id=report.message_id,
        room_id=report.room_id,
        reporter_session_id=OTHER_REPORTER_ID,
        reason="spam",
        status="pending",
        created_at=datetime.now(UTC),
    )
    db.add(second)
    db.commit()
    published: list[tuple[str, str, dict[str, str]]] = []
    monkeypatch.setattr(
        "app.api.reports.publish",
        lambda topic, event, payload: published.append((topic, event, payload)),
    )

    response = client.post(f"/api/v1/admin/reports/{report.id}/remove-message")

    assert response.status_code == 204
    message = db.get(Message, report.message_id)
    assert message is not None
    assert message.removed_at is not None
    assert message.removed_by == ADMIN_ID
    assert {item.status for item in db.scalars(select(Report))} == {"removed"}
    assert published == [
        (f"room:{report.room_id}", "message.removed", {"id": str(report.message_id)})
    ]


def test_dismiss_report_is_no_longer_pending(client: TestClient, db: Session) -> None:
    report = add_report(db)

    response = client.post(f"/api/v1/admin/reports/{report.id}/dismiss")

    assert response.status_code == 204
    db.refresh(report)
    assert report.status == "dismissed"
    assert report.handled_at is not None
    assert report.handled_by == ADMIN_ID


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [(Unauthenticated, 401, "UNAUTHENTICATED"), (Forbidden, 403, "FORBIDDEN")],
)
def test_report_actions_require_admin(
    app: Any, db: Session, error: type[Exception], status: int, code: str
) -> None:
    report = add_report(db)

    def reject() -> Admin:
        raise error()

    app.dependency_overrides[require_admin] = reject
    with TestClient(app) as client:
        response = client.post(f"/api/v1/admin/reports/{report.id}/dismiss")

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
