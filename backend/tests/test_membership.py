"""Membership queries run against SQLite; its advisory-lock shim does not test PG locking."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import Session as Identity
from app.core.auth import get_current_session
from app.core.config import Settings
from app.core.db import Base, get_db
from app.core.errors import NotAMember, RoomNotFound
from app.main import create_app
from app.modules.nicknames import service as nicknames
from app.modules.rooms import presence, repository, service
from app.modules.rooms.models import Room, RoomMember, RoomPresenceCount

NOW = datetime(2026, 10, 15, 20, 0, tzinfo=UTC)
SESSION_ID = uuid4()


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    locks: list[int] = []
    statements: list[str] = []

    @event.listens_for(engine, "connect")
    def configure(connection, record) -> None:
        connection.execute("pragma foreign_keys=on")
        connection.create_function("pg_advisory_xact_lock", 1, lambda key: locks.append(key))

    @event.listens_for(engine, "before_cursor_execute")
    def record_sql(connection, cursor, statement, parameters, context, many) -> None:
        statements.append(statement)

    Base.metadata.create_all(engine)
    monkeypatch.setattr(service, "utc_now", lambda: NOW)
    with Session(engine, expire_on_commit=False) as session:
        session.info.update(locks=locks, statements=statements)
        yield session
    engine.dispose()


def add_room(db: Session, status: str = "active") -> UUID:
    room_id = uuid4()
    db.add(
        Room(
            id=room_id,
            name=f"Test Room {room_id}",
            description="A test room.",
            category="library",
            latitude=29.65,
            longitude=-82.34,
            status=status,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    db.commit()
    return room_id


@pytest.fixture
def room_id(db: Session) -> UUID:
    return add_room(db)


def add_member(
    db: Session,
    room_id: UUID,
    *,
    session_id: UUID = SESSION_ID,
    nickname: str = "Quiet Otter",
    age: float = 0,
    left: bool = False,
) -> None:
    db.add(
        RoomMember(
            room_id=room_id,
            session_id=session_id,
            nickname=nickname,
            joined_at=NOW - timedelta(minutes=5),
            last_seen_at=NOW - timedelta(seconds=age),
            left_at=NOW - timedelta(seconds=1) if left else None,
        )
    )
    db.commit()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_session] = lambda: Identity(str(SESSION_ID), True)
    with TestClient(app) as result:
        yield result


def test_join_response_and_token_identity(client: TestClient, db: Session, room_id: UUID) -> None:
    response = client.post(f"/api/v1/rooms/{room_id}/join", json={"session_id": str(uuid4())})
    assert response.status_code == 200
    assert set(response.json()) == {"room", "nickname"}
    assert response.json()["room"] == {
        "id": str(room_id),
        "name": f"Test Room {room_id}",
        "description": "A test room.",
    }
    assert response.json()["nickname"]
    assert not db.in_transaction()
    member = db.get(RoomMember, (room_id, SESSION_ID))
    assert member is not None
    assert member.nickname == response.json()["nickname"]
    assert member.last_seen_at.replace(tzinfo=UTC) == NOW
    assert member.joined_at.replace(tzinfo=UTC) == NOW
    assert member.left_at is None
    assert db.scalar(select(func.count()).select_from(RoomMember)) == 1


@pytest.mark.parametrize("age", [0, 30, 31, 59, 59.999, 60])
def test_rejoin_keeps_reserved_nickname(
    client: TestClient,
    db: Session,
    room_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    age: float,
) -> None:
    add_member(db, room_id, age=age)
    generator = Mock(side_effect=AssertionError("A reserved nickname must be reused"))
    monkeypatch.setattr(service, "generate_nickname", generator)
    assert client.post(f"/api/v1/rooms/{room_id}/join").json()["nickname"] == "Quiet Otter"
    assert client.post(f"/api/v1/rooms/{room_id}/join").json()["nickname"] == "Quiet Otter"
    assert db.scalar(select(func.count()).select_from(RoomMember)) == 1
    generator.assert_not_called()


@pytest.mark.parametrize("age,left", [(60.000001, False), (61, False), (120, False), (0, True)])
def test_expired_or_left_rejoin_cannot_redraw_previous_nickname(
    client: TestClient,
    db: Session,
    room_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    age: float,
    left: bool,
) -> None:
    add_member(db, room_id, age=age, left=left)
    # Exercise the real generator, deterministically preferring the caller's old
    # name whenever it is eligible. A lucky random draw must not hide a regression.
    monkeypatch.setattr(
        nicknames,
        "choice",
        lambda available: next(name for name in ("Quiet Otter", "Calm Fox") if name in available),
    )
    generator = Mock(wraps=service.generate_nickname)
    monkeypatch.setattr(service, "generate_nickname", generator)
    response = client.post(f"/api/v1/rooms/{room_id}/join")
    assert response.status_code == 200
    assert response.json()["nickname"] == "Calm Fox"
    generator.assert_called_once_with({"Quiet Otter"})
    member = db.get(RoomMember, (room_id, SESSION_ID))
    assert member.left_at is None
    assert member.joined_at.replace(tzinfo=UTC) == NOW
    assert member.last_seen_at.replace(tzinfo=UTC) == NOW
    assert db.scalar(select(func.count()).select_from(RoomMember)) == 1


def test_all_and_only_reserved_room_names_passed_to_generator(
    client: TestClient,
    db: Session,
    room_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, age, left in [
        ("Quiet Otter", 0, False),
        ("Bright Fox", 60, False),
        ("Calm Bunny", 60.001, False),
        ("Happy Panda", 0, True),
    ]:
        add_member(db, room_id, session_id=uuid4(), nickname=name, age=age, left=left)
    other_room = add_room(db)
    add_member(db, other_room, nickname="Wise Owl")
    generator = Mock(return_value="Sunny Fox")
    monkeypatch.setattr(service, "generate_nickname", generator)
    assert client.post(f"/api/v1/rooms/{room_id}/join").status_code == 200
    generator.assert_called_once_with({"Quiet Otter", "Bright Fox"})


@pytest.mark.parametrize("age,expected", [(59, "Calm Fox"), (60, "Calm Fox"), (61, "Quiet Otter")])
def test_other_session_can_claim_name_only_after_hold_expires(
    client: TestClient,
    db: Session,
    room_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    age: float,
    expected: str,
) -> None:
    def choose(taken: set[str]) -> str:
        return next(name for name in ["Quiet Otter", "Calm Fox"] if name not in taken)

    monkeypatch.setattr(service, "generate_nickname", choose)
    add_member(db, room_id, session_id=uuid4(), age=age)
    response = client.post(f"/api/v1/rooms/{room_id}/join")
    assert response.status_code == 200
    assert response.json()["nickname"] == expected


def test_lock_first_and_same_key_for_same_room(
    client: TestClient, db: Session, room_id: UUID
) -> None:
    db.info["statements"].clear()
    assert client.post(f"/api/v1/rooms/{room_id}/join").status_code == 200
    assert "pg_advisory_xact_lock" in db.info["statements"][0]
    assert not db.in_transaction()
    assert client.post(f"/api/v1/rooms/{room_id}/join").status_code == 200
    assert db.info["locks"][0] == db.info["locks"][1]
    other_room = add_room(db)
    assert client.post(f"/api/v1/rooms/{other_room}/join").status_code == 200
    assert db.info["locks"][0] != db.info["locks"][2]
    assert all(-(2**63) <= key < 2**63 for key in db.info["locks"])


def test_join_rolls_back_after_write_failure(
    client: TestClient,
    db: Session,
    room_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = repository.upsert_member

    def fail_after_flush(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("test failure after flush")

    monkeypatch.setattr(repository, "upsert_member", fail_after_flush)
    with pytest.raises(RuntimeError, match="after flush"):
        client.post(f"/api/v1/rooms/{room_id}/join")
    assert not db.in_transaction()
    assert db.scalar(select(func.count()).select_from(RoomMember)) == 0


@pytest.mark.parametrize("endpoint", ["join", "heartbeat", "leave"])
@pytest.mark.parametrize("state", ["missing", "archived"])
def test_inactive_room_returns_404(
    client: TestClient, db: Session, endpoint: str, state: str
) -> None:
    target = uuid4() if state == "missing" else add_room(db, "archived")
    response = client.post(f"/api/v1/rooms/{target}/{endpoint}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROOM_NOT_FOUND"


@pytest.mark.parametrize("endpoint", ["join", "heartbeat", "leave"])
@pytest.mark.parametrize("header", [None, "Basic invalid", "Bearer invalid"])
def test_membership_routes_require_auth(
    client: TestClient,
    room_id: UUID,
    endpoint: str,
    header: str | None,
) -> None:
    client.app.dependency_overrides.pop(get_current_session)
    response = client.post(
        f"/api/v1/rooms/{room_id}/{endpoint}", headers={"Authorization": header} if header else {}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("left", [False, True])
def test_heartbeat_does_not_create_or_revive_membership(
    client: TestClient,
    db: Session,
    room_id: UUID,
    left: bool,
) -> None:
    if left:
        add_member(db, room_id, left=True, age=30)
    response = client.post(f"/api/v1/rooms/{room_id}/heartbeat")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_A_MEMBER"
    member = db.get(RoomMember, (room_id, SESSION_ID))
    if left:
        assert member.left_at is not None
        assert member.last_seen_at.replace(tzinfo=UTC) == NOW - timedelta(seconds=30)
    else:
        assert member is None


@pytest.mark.parametrize("age", [15, 31, 120])
def test_heartbeat_refreshes_only_last_seen(
    client: TestClient,
    db: Session,
    room_id: UUID,
    age: float,
) -> None:
    add_member(db, room_id, age=age)
    response = client.post(f"/api/v1/rooms/{room_id}/heartbeat")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    member = db.get(RoomMember, (room_id, SESSION_ID))
    assert member.nickname == "Quiet Otter"
    assert member.joined_at.replace(tzinfo=UTC) == NOW - timedelta(minutes=5)
    assert member.last_seen_at.replace(tzinfo=UTC) == NOW
    assert member.left_at is None


@pytest.mark.parametrize("age", [0, 31, 61, 120])
def test_ensure_member_is_independent_of_presence_and_reservation(
    db: Session, room_id: UUID, age: float
) -> None:
    add_member(db, room_id, age=age)
    membership = service.ensure_member(db, str(SESSION_ID), str(room_id))
    assert isinstance(membership, service.Membership)
    assert membership.room_id == str(room_id)
    assert membership.session_id == str(SESSION_ID)
    assert membership.nickname == "Quiet Otter"
    assert membership.joined_at.replace(tzinfo=UTC) == NOW - timedelta(minutes=5)


@pytest.mark.parametrize("left", [False, True])
def test_ensure_member_rejects_never_joined_and_left(
    db: Session, room_id: UUID, left: bool
) -> None:
    if left:
        add_member(db, room_id, left=True)
    with pytest.raises(NotAMember):
        service.ensure_member(db, str(SESSION_ID), str(room_id))


@pytest.mark.parametrize("state", ["missing", "archived"])
def test_ensure_member_checks_active_room_first(db: Session, state: str) -> None:
    target = uuid4() if state == "missing" else add_room(db, "archived")
    with pytest.raises(RoomNotFound):
        service.ensure_member(db, str(SESSION_ID), str(target))


def counts(client: TestClient, db: Session) -> dict[str, int]:
    response = client.get("/api/v1/rooms")
    assert response.status_code == 200
    # HTTP requests normally get separate sessions; this fixture shares one.
    db.rollback()
    return {room["id"]: room["participant_count"] for room in response.json()}


def test_leave_changes_only_the_token_callers_room(
    client: TestClient, db: Session, room_id: UUID
) -> None:
    other_user = uuid4()
    other_room = add_room(db)
    for target in (room_id, other_room):
        add_member(db, target, age=15)
        add_member(db, target, session_id=other_user, nickname="Calm Fox")
    before = counts(client, db)
    db.info["statements"].clear()
    response = client.post(
        f"/api/v1/rooms/{room_id}/leave",
        json={"session_id": str(other_user), "room_id": str(other_room)},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not db.in_transaction()
    assert "pg_advisory_xact_lock" in db.info["statements"][0]
    assert db.info["locks"][-1] == repository.room_lock_key(room_id)
    for target in (room_id, other_room):
        for user in (SESSION_ID, other_user):
            member = db.get(RoomMember, (target, user))
            assert member.nickname == ("Quiet Otter" if user == SESSION_ID else "Calm Fox")
            assert member.joined_at.replace(tzinfo=UTC) == NOW - timedelta(minutes=5)
            assert member.last_seen_at.replace(tzinfo=UTC) == NOW - timedelta(
                seconds=15 if user == SESSION_ID else 0
            )
            if (target, user) == (room_id, SESSION_ID):
                assert member.left_at.replace(tzinfo=UTC) == NOW
            else:
                assert member.left_at is None
    after = counts(client, db)
    assert (before[str(room_id)], after[str(room_id)]) == (2, 1)
    assert before[str(other_room)] == after[str(other_room)] == 2
    with pytest.raises(NotAMember):
        service.ensure_member(db, str(SESSION_ID), str(room_id))
    db.rollback()
    response = client.post(f"/api/v1/rooms/{room_id}/heartbeat")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_A_MEMBER"


@pytest.mark.parametrize("left", [False, True])
def test_leave_rejects_missing_or_already_left_membership(
    client: TestClient, db: Session, room_id: UUID, left: bool
) -> None:
    if left:
        add_member(db, room_id, left=True, age=15)
    response = client.post(f"/api/v1/rooms/{room_id}/leave")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_A_MEMBER"
    assert not db.in_transaction()
    member = db.get(RoomMember, (room_id, SESSION_ID))
    if left:
        assert member.left_at.replace(tzinfo=UTC) == NOW - timedelta(seconds=1)
        assert member.last_seen_at.replace(tzinfo=UTC) == NOW - timedelta(seconds=15)
    else:
        assert member is None


def test_stale_member_can_explicitly_leave(client: TestClient, db: Session, room_id: UUID) -> None:
    add_member(db, room_id, age=120)
    assert client.post(f"/api/v1/rooms/{room_id}/leave").status_code == 200
    assert counts(client, db)[str(room_id)] == 0


@pytest.mark.parametrize("other_claims_name", [False, True])
def test_leave_frees_nickname_and_rejoin_allocates_fresh_name(
    client: TestClient,
    db: Session,
    room_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
    other_claims_name: bool,
) -> None:
    generator = Mock(
        side_effect=lambda taken: next(
            name for name in ("Quiet Otter", "Calm Fox") if name not in taken
        )
    )
    monkeypatch.setattr(service, "generate_nickname", generator)
    path = f"/api/v1/rooms/{room_id}"
    assert client.post(f"{path}/join").json()["nickname"] == "Quiet Otter"
    assert counts(client, db)[str(room_id)] == 1
    assert client.post(f"{path}/leave").status_code == 200
    assert counts(client, db)[str(room_id)] == 0
    if other_claims_name:
        other_user = uuid4()
        client.app.dependency_overrides[get_current_session] = lambda: Identity(
            str(other_user), True
        )
        assert client.post(f"{path}/join").json()["nickname"] == "Quiet Otter"
        generator.assert_called_with(set())
    client.app.dependency_overrides[get_current_session] = lambda: Identity(str(SESSION_ID), True)
    assert client.post(f"{path}/join").json()["nickname"] == "Calm Fox"
    generator.assert_called_with({"Quiet Otter"})
    assert counts(client, db)[str(room_id)] == (2 if other_claims_name else 1)
    member = db.get(RoomMember, (room_id, SESSION_ID))
    assert member.left_at is None
    assert member.joined_at.replace(tzinfo=UTC) == NOW
    assert member.last_seen_at.replace(tzinfo=UTC) == NOW


def test_leave_rolls_back_after_write_failure(
    client: TestClient, db: Session, room_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_member(db, room_id)
    original = repository.leave

    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("test failure after leave write")

    monkeypatch.setattr(repository, "leave", fail_after_write)
    with pytest.raises(RuntimeError, match="after leave write"):
        client.post(f"/api/v1/rooms/{room_id}/leave")
    assert not db.in_transaction()
    assert db.get(RoomMember, (room_id, SESSION_ID)).left_at is None
    assert counts(client, db)[str(room_id)] == 1


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    current = [NOW]
    monkeypatch.setattr(service, "utc_now", lambda: current[0])
    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None))
    return current


CountEvents = list[tuple[str, str, dict[str, str | int]]]


def count_events(room_id: UUID, *values: int) -> CountEvents:
    return [
        event
        for count in values
        for event in (
            (f"room:{room_id}", "presence.updated", {"count": count}),
            ("rooms", "room.count", {"room_id": str(room_id), "count": count}),
        )
    ]


@pytest.fixture
def published(db: Session, monkeypatch: pytest.MonkeyPatch) -> CountEvents:
    events: CountEvents = []

    def record(topic: str, event: str, payload: dict[str, str | int]) -> None:
        assert not db.in_transaction(), "Count events must be published after commit"
        events.append((topic, event, payload))

    monkeypatch.setattr(presence, "publish", record)
    return events


def test_join_and_leave_publish_exact_counts(
    client: TestClient, room_id: UUID, published: CountEvents, clock: list[datetime]
) -> None:
    path = f"/api/v1/rooms/{room_id}"
    assert client.post(f"{path}/join").status_code == 200
    other_user = uuid4()
    client.app.dependency_overrides[get_current_session] = lambda: Identity(str(other_user), True)
    assert client.post(f"{path}/join").status_code == 200
    assert client.post(f"{path}/leave").json() == {"status": "ok"}
    client.app.dependency_overrides[get_current_session] = lambda: Identity(str(SESSION_ID), True)
    assert client.post(f"{path}/leave").json() == {"status": "ok"}
    assert published == count_events(room_id, 1, 2, 1, 0)


def test_unchanged_and_failed_operations_do_not_publish(
    client: TestClient, db: Session, room_id: UUID, published: CountEvents, clock: list[datetime]
) -> None:
    path = f"/api/v1/rooms/{room_id}"
    assert client.post(f"{path}/join").status_code == 200
    published.clear()
    assert client.post(f"{path}/join").status_code == 200
    clock[0] += timedelta(seconds=30)
    assert client.post(f"{path}/heartbeat").status_code == 200
    service.sweep_room_presence(db, room_id)
    assert published == []
    assert client.post(f"{path}/leave").status_code == 200
    published.clear()
    assert client.post(f"{path}/leave").status_code == 403
    assert client.post(f"{path}/heartbeat").status_code == 403
    assert client.post(f"/api/v1/rooms/{uuid4()}/join").status_code == 404
    service.sweep_room_presence(db, room_id)
    assert published == []


@pytest.mark.parametrize("timeout", [10, 30])
def test_sweeps_include_exact_boundary_and_expire_once(
    client: TestClient,
    db: Session,
    room_id: UUID,
    published: CountEvents,
    clock: list[datetime],
    monkeypatch: pytest.MonkeyPatch,
    timeout: int,
) -> None:
    monkeypatch.setattr(
        service, "get_settings", lambda: Settings(_env_file=None, presence_timeout_seconds=timeout)
    )
    assert client.post(f"/api/v1/rooms/{room_id}/join").status_code == 200
    published.clear()
    for seconds in (timeout - 0.000001, timeout):
        clock[0] = NOW + timedelta(seconds=seconds)
        service.sweep_room_presence(db, room_id)
        assert counts(client, db)[str(room_id)] == 1
        assert published == []
    clock[0] += timedelta(microseconds=1)
    service.sweep_room_presence(db, room_id)
    assert published == count_events(room_id, 0)
    for seconds in (timeout + 1, 60, 120):
        clock[0] = NOW + timedelta(seconds=seconds)
        service.sweep_room_presence(db, room_id)
    assert published == count_events(room_id, 0)
    assert counts(client, db)[str(room_id)] == 0
    assert service.ensure_member(db, str(SESSION_ID), str(room_id)).nickname


@pytest.mark.parametrize("endpoint", ["join", "heartbeat"])
def test_returning_member_restores_count_without_duplicates(
    client: TestClient,
    db: Session,
    room_id: UUID,
    published: CountEvents,
    clock: list[datetime],
    endpoint: str,
) -> None:
    path = f"/api/v1/rooms/{room_id}"
    nickname = client.post(f"{path}/join").json()["nickname"]
    clock[0] += timedelta(seconds=15)
    other_user = uuid4()
    client.app.dependency_overrides[get_current_session] = lambda: Identity(str(other_user), True)
    assert client.post(f"{path}/join").status_code == 200
    clock[0] = NOW + timedelta(seconds=31)
    published.clear()
    service.sweep_room_presence(db, room_id)
    assert published == count_events(room_id, 1)
    client.app.dependency_overrides[get_current_session] = lambda: Identity(str(SESSION_ID), True)
    assert client.post(f"{path}/{endpoint}").status_code == 200
    assert client.post(f"{path}/{endpoint}").status_code == 200
    service.sweep_room_presence(db, room_id)
    assert published == count_events(room_id, 1, 2)
    assert counts(client, db)[str(room_id)] == 2
    member = db.get(RoomMember, (room_id, SESSION_ID))
    assert member.nickname == nickname
    assert member.left_at is None
    assert member.joined_at.replace(tzinfo=UTC) == (clock[0] if endpoint == "join" else NOW)


@pytest.mark.parametrize("returning", [False, True])
def test_presence_refresh_before_sweep_does_not_duplicate_count(
    client: TestClient,
    db: Session,
    room_id: UUID,
    published: CountEvents,
    clock: list[datetime],
    returning: bool,
) -> None:
    assert client.post(f"/api/v1/rooms/{room_id}/join").status_code == 200
    published.clear()
    clock[0] += timedelta(seconds=31)
    if not returning:
        client.app.dependency_overrides[get_current_session] = lambda: Identity(str(uuid4()), True)
    assert client.post(f"/api/v1/rooms/{room_id}/join").status_code == 200
    service.sweep_room_presence(db, room_id)
    assert counts(client, db)[str(room_id)] == 1
    assert published == []


def test_timeout_preserves_nickname_reservation_and_joined_membership(
    client: TestClient,
    db: Session,
    room_id: UUID,
    published: CountEvents,
    clock: list[datetime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "generate_nickname",
        lambda taken: next(name for name in ("Quiet Otter", "Calm Fox") if name not in taken),
    )
    path = f"/api/v1/rooms/{room_id}"
    assert client.post(f"{path}/join").json()["nickname"] == "Quiet Otter"
    clock[0] += timedelta(seconds=31)
    service.sweep_room_presence(db, room_id)
    membership = service.ensure_member(db, str(SESSION_ID), str(room_id))
    assert membership.nickname == "Quiet Otter"
    member = db.get(RoomMember, (room_id, SESSION_ID))
    assert member.left_at is None
    assert member.last_seen_at.replace(tzinfo=UTC) == NOW
    assert member.joined_at.replace(tzinfo=UTC) == NOW
    db.rollback()
    other_user = uuid4()
    client.app.dependency_overrides[get_current_session] = lambda: Identity(str(other_user), True)
    assert client.post(f"{path}/join").json()["nickname"] == "Calm Fox"
    clock[0] = NOW + timedelta(seconds=60)
    client.app.dependency_overrides[get_current_session] = lambda: Identity(str(SESSION_ID), True)
    assert client.post(f"{path}/join").json()["nickname"] == "Quiet Otter"
    assert published == count_events(room_id, 1, 0, 1, 2)


def test_leave_after_timeout_does_not_publish_again(
    client: TestClient, db: Session, room_id: UUID, published: CountEvents, clock: list[datetime]
) -> None:
    path = f"/api/v1/rooms/{room_id}"
    assert client.post(f"{path}/join").status_code == 200
    clock[0] += timedelta(seconds=31)
    service.sweep_room_presence(db, room_id)
    published.clear()
    assert client.post(f"{path}/leave").status_code == 200
    service.sweep_room_presence(db, room_id)
    assert published == []
    assert db.get(RoomMember, (room_id, SESSION_ID)).left_at is not None


@pytest.mark.parametrize("operation", ["join", "leave", "heartbeat", "sweep"])
def test_publish_failures_leave_changes_committed(
    client: TestClient,
    db: Session,
    room_id: UUID,
    clock: list[datetime],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    operation: str,
) -> None:
    path = f"/api/v1/rooms/{room_id}"
    if operation != "join":
        assert client.post(f"{path}/join").status_code == 200
    if operation in {"heartbeat", "sweep"}:
        clock[0] += timedelta(seconds=31)
    if operation == "heartbeat":
        service.sweep_room_presence(db, room_id)

    def fail(*args) -> None:
        assert not db.in_transaction()
        raise RuntimeError("test transport failure")

    publisher = Mock(side_effect=fail)
    monkeypatch.setattr(presence, "publish", publisher)
    if operation == "sweep":
        service.sweep_room_presence(db, room_id)
    else:
        assert client.post(f"{path}/{operation}").status_code == 200
    assert publisher.call_count == 2
    assert "Participant count publish failed" in caplog.text
    assert not db.in_transaction()
    member = db.get(RoomMember, (room_id, SESSION_ID))
    assert (member.left_at is not None) == (operation == "leave")
    if operation == "heartbeat":
        assert member.last_seen_at.replace(tzinfo=UTC) == clock[0]
    state = db.get(RoomPresenceCount, room_id)
    assert state.participant_count == (0 if operation in {"leave", "sweep"} else 1)


def test_failed_observation_rolls_back_and_next_sweep_retries(
    client: TestClient,
    db: Session,
    room_id: UUID,
    published: CountEvents,
    clock: list[datetime],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client.post(f"/api/v1/rooms/{room_id}/join").status_code == 200
    published.clear()
    clock[0] += timedelta(seconds=31)
    original = repository.refresh_presence_count

    def fail_after_observation(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("test observation failure")

    monkeypatch.setattr(repository, "refresh_presence_count", fail_after_observation)
    with pytest.raises(RuntimeError, match="observation failure"):
        service.sweep_room_presence(db, room_id)
    assert not db.in_transaction()
    assert published == []
    assert db.get(RoomPresenceCount, room_id).participant_count == 1
    assert db.get(RoomMember, (room_id, SESSION_ID)).left_at is None
    db.rollback()
    monkeypatch.setattr(repository, "refresh_presence_count", original)
    service.sweep_room_presence(db, room_id)
    assert published == count_events(room_id, 0)


def test_first_sweep_finds_old_members_and_ignores_archived_rooms(
    db: Session, room_id: UUID, published: CountEvents, clock: list[datetime]
) -> None:
    add_member(db, room_id, age=31)
    archived = add_room(db, "archived")
    add_member(db, archived, age=31)
    empty = add_room(db)
    for target in (room_id, archived, empty, uuid4()):
        service.sweep_room_presence(db, target)
    assert published == count_events(room_id, 0)
    # A new session (like a restarted worker) must not repeat an observed timeout.
    with Session(db.get_bind()) as fresh:
        service.sweep_room_presence(fresh, room_id)
    assert published == count_events(room_id, 0)


@pytest.mark.parametrize("endpoint", ["join", "leave", "heartbeat"])
def test_commit_failure_never_publishes_membership_or_count_changes(
    client: TestClient,
    db: Session,
    room_id: UUID,
    published: CountEvents,
    clock: list[datetime],
    endpoint: str,
) -> None:
    path = f"/api/v1/rooms/{room_id}"
    if endpoint != "join":
        assert client.post(f"{path}/join").status_code == 200
    if endpoint == "heartbeat":
        clock[0] += timedelta(seconds=31)
        service.sweep_room_presence(db, room_id)
    published.clear()

    def fail_commit(session):
        raise RuntimeError("test commit failure")

    event.listen(db, "before_commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="commit failure"):
            client.post(f"{path}/{endpoint}")
    finally:
        event.remove(db, "before_commit", fail_commit)
    assert not db.in_transaction()
    assert published == []
    member = db.get(RoomMember, (room_id, SESSION_ID))
    state = db.get(RoomPresenceCount, room_id)
    if endpoint == "join":
        assert member is None
        assert state is None
    else:
        assert member.left_at is None
        assert member.last_seen_at.replace(tzinfo=UTC) == NOW
        assert state.participant_count == (0 if endpoint == "heartbeat" else 1)
    db.rollback()
    assert client.post(f"{path}/{endpoint}").status_code == 200
    assert published == count_events(room_id, 0 if endpoint == "leave" else 1)
