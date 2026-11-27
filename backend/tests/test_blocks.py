"""Temporary blocks through real authorization, sender resolution, and the send pipeline."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from functools import partial
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import Session as Identity
from app.core.auth import get_current_session
from app.core.auth_models import AdminUser
from app.core.config import Settings
from app.core.db import Base, get_db
from app.main import create_app
from app.modules.messaging import service as messaging
from app.modules.messaging.models import Message
from app.modules.rooms.models import Room, RoomMember
from app.modules.safety import blocks
from app.modules.safety.models import Block, Report

NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)
ADMIN_ID = uuid4()
SENDER_ID = uuid4()
REPORTER_ID = uuid4()
OTHER_SENDER_ID = uuid4()
PATH = "/api/v1/admin/blocks"


@pytest.fixture(params=["sqlite", "postgres"])
def db(request: pytest.FixtureRequest) -> Iterator[Session]:
    if request.param == "postgres":
        engine = request.getfixturevalue("pg_engine")
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
    with engine.connect() as connection, connection.begin() as transaction:
        with Session(
            connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        transaction.rollback()
    if request.param == "sqlite":
        engine.dispose()


@pytest.fixture
def report(db: Session) -> Report:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("INSERT INTO auth.users (id) VALUES (:id)"),
            [{"id": value} for value in (ADMIN_ID, SENDER_ID, REPORTER_ID, OTHER_SENDER_ID)],
        )
    db.add(AdminUser(user_id=ADMIN_ID, display_name="Test admin", created_at=NOW))
    rooms = []
    for name in ("Library West", "Marston Science Library"):
        room = Room(
            id=uuid4(),
            name=name,
            description="Test room",
            category="library",
            latitude=29.65,
            longitude=-82.34,
            status="active",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(room)
        db.flush()
        rooms.append(room)
        for session_id, nickname in (
            (SENDER_ID, "Quiet Otter"),
            (OTHER_SENDER_ID, "Calm Fox"),
            (REPORTER_ID, "Brave Bird"),
        ):
            db.add(
                RoomMember(
                    room_id=room.id,
                    session_id=session_id,
                    nickname=nickname,
                    joined_at=NOW,
                    last_seen_at=NOW,
                )
            )
    message = Message(
        id=uuid4(),
        room_id=rooms[0].id,
        session_id=SENDER_ID,
        nickname="Quiet Otter",
        body="Reported content",
        created_at=NOW,
    )
    # A different session can use the same nickname in a different room.
    other_message = Message(
        id=uuid4(),
        room_id=rooms[1].id,
        session_id=OTHER_SENDER_ID,
        nickname="Quiet Otter",
        body="Unrelated content",
        created_at=NOW,
    )
    db.add_all([message, other_message])
    db.flush()
    report = Report(
        id=uuid4(),
        message_id=message.id,
        room_id=message.room_id,
        reporter_session_id=REPORTER_ID,
        reason="harassment",
        status="pending",
        created_at=NOW,
    )
    db.add(report)
    db.commit()
    return report


@pytest.fixture
def app(db: Session, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(blocks, "utc_now", lambda: NOW)
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    # Exercise the real require_admin allow-list check; JWT verification has its own suite.
    app.dependency_overrides[get_current_session] = lambda: Identity(str(ADMIN_ID), False)
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def create_block(client: TestClient, report: Report, minutes: int = 15):
    return client.post(PATH, json={"report_id": str(report.id), "duration_minutes": minutes})


@pytest.mark.parametrize("minutes", [15, 60, 1440])
def test_admin_blocks_the_reported_sender(
    client: TestClient, db: Session, report: Report, minutes: int
) -> None:
    response = create_block(client, report, minutes)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "created_at", "expires_at"}
    assert datetime.fromisoformat(body["created_at"]) == NOW
    assert datetime.fromisoformat(body["expires_at"]) == NOW + timedelta(minutes=minutes)
    block = db.get(Block, UUID(body["id"]))
    assert block.session_id == SENDER_ID
    assert block.session_id not in {REPORTER_ID, ADMIN_ID, OTHER_SENDER_ID}
    assert (block.reason, block.created_by) == ("harassment", ADMIN_ID)
    db.refresh(report)
    assert report.status == "pending"
    assert db.get(Message, report.message_id).removed_at is None


@pytest.mark.parametrize("anonymous,listed", [(True, False), (True, True), (False, False)])
def test_non_admin_cannot_block(
    app: FastAPI, client: TestClient, db: Session, report: Report, anonymous: bool, listed: bool
) -> None:
    caller = ADMIN_ID if listed else REPORTER_ID
    app.dependency_overrides[get_current_session] = lambda: Identity(str(caller), anonymous)

    response = create_block(client, report)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert db.scalars(select(Block)).all() == []


def test_missing_token_cannot_block(
    app: FastAPI, client: TestClient, db: Session, report: Report
) -> None:
    del app.dependency_overrides[get_current_session]

    response = create_block(client, report)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"
    assert db.scalars(select(Block)).all() == []


@pytest.mark.parametrize("duration", [0, -15, 30, 1441, 15.0, 15.5, "15", True, None])
def test_invalid_duration_is_rejected(
    client: TestClient, db: Session, report: Report, duration: object
) -> None:
    response = client.post(PATH, json={"report_id": str(report.id), "duration_minutes": duration})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert db.scalars(select(Block)).all() == []


def test_duration_respects_configured_options(
    client: TestClient, db: Session, report: Report, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.modules.safety.schemas.get_settings",
        lambda: Settings(_env_file=None, block_duration_options_minutes=(15, 60)),
    )
    assert create_block(client, report, 1440).status_code == 422
    assert db.scalars(select(Block)).all() == []


@pytest.mark.parametrize("extra", [{"session_id": str(REPORTER_ID)}, {"room_id": str(uuid4())}])
def test_caller_cannot_choose_the_blocked_session_or_room(
    client: TestClient, db: Session, report: Report, extra: dict[str, str]
) -> None:
    response = client.post(
        PATH, json={"report_id": str(report.id), "duration_minutes": 15, **extra}
    )
    assert response.status_code == 422
    assert db.scalars(select(Block)).all() == []


def test_missing_report_returns_404(client: TestClient, db: Session, report: Report) -> None:
    response = client.post(PATH, json={"report_id": str(uuid4()), "duration_minutes": 15})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REPORT_NOT_FOUND"
    assert db.scalars(select(Block)).all() == []


@pytest.mark.parametrize("status", ["removed", "dismissed"])
def test_retained_report_can_still_identify_sender(
    client: TestClient, db: Session, report: Report, status: str
) -> None:
    report.status = status
    if status == "removed":
        message = db.get(Message, report.message_id)
        message.removed_at, message.removed_by = NOW, ADMIN_ID
    db.commit()
    assert create_block(client, report).status_code == 200
    assert db.scalar(select(Block.session_id)) == SENDER_ID


def test_shorter_repeat_block_cannot_end_a_longer_block_early(
    client: TestClient, db: Session, report: Report, monkeypatch: pytest.MonkeyPatch
) -> None:
    longer = create_block(client, report, 1440).json()["expires_at"]
    monkeypatch.setattr(blocks, "utc_now", lambda: NOW + timedelta(minutes=1))
    shorter = create_block(client, report, 15)
    assert shorter.status_code == 200
    assert datetime.fromisoformat(shorter.json()["expires_at"]) == datetime.fromisoformat(longer)
    assert len(db.scalars(select(Block)).all()) == 2
    with pytest.raises(blocks.Blocked) as error:
        blocks.check_not_blocked(db, str(SENDER_ID))
    assert datetime.fromisoformat(error.value.extra["until"]) == NOW + timedelta(days=1)


def test_send_pipeline_blocks_across_rooms_until_exact_expiry(
    app: FastAPI,
    client: TestClient,
    db: Session,
    report: Report,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = create_block(client, report)
    assert response.status_code == 200
    until = datetime.fromisoformat(response.json()["expires_at"])
    rooms = db.scalars(select(Room.id).order_by(Room.name)).all()
    published = []
    monkeypatch.setattr(messaging, "publish", lambda *event: published.append(event))
    app.dependency_overrides[get_current_session] = lambda: Identity(str(SENDER_ID), True)

    for now in (NOW, until - timedelta(microseconds=1)):
        monkeypatch.setattr(blocks, "utc_now", lambda now=now: now)
        for room_id in rooms:
            # The block check precedes content validation as pipeline step 2.
            rejected = client.post(f"/api/v1/rooms/{room_id}/messages", json={"body": "   "})
            assert rejected.status_code == 403
            error = rejected.json()["error"]
            assert error["code"] == "BLOCKED"
            assert error["message"]
            assert datetime.fromisoformat(error["until"]) == until
    assert len(db.scalars(select(Message)).all()) == 2
    assert published == []

    # The reporter and another sender sharing the IP/nickname are unaffected.
    for caller in (REPORTER_ID, OTHER_SENDER_ID):
        app.dependency_overrides[get_current_session] = partial(Identity, str(caller), True)
        assert (
            client.post(
                f"/api/v1/rooms/{rooms[1]}/messages", json={"body": "Still allowed"}
            ).status_code
            == 201
        )

    app.dependency_overrides[get_current_session] = lambda: Identity(str(SENDER_ID), True)
    for now, room_id in zip((until, until + timedelta(microseconds=1)), rooms, strict=True):
        monkeypatch.setattr(blocks, "utc_now", lambda now=now: now)
        accepted = client.post(f"/api/v1/rooms/{room_id}/messages", json={"body": "Allowed again"})
        assert accepted.status_code == 201
    assert len(published) == 4
    # Expiry leaves the audit record in place; no cleanup job is required.
    assert len(db.scalars(select(Block)).all()) == 1
