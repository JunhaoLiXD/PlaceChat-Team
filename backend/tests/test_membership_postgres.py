"""Real migrations, locks, and RLS on a disposable, loopback-only PostgreSQL database.

Set TEST_DATABASE_URL to a local placechat_pbi07_* database on a disposable server.
The fixture creates and drops its own database; it never reads the application's DATABASE_URL.
Only auth.users' UUID key is stubbed: full Supabase Auth remains a live smoke check.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, event, inspect, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotAMember
from app.modules.rooms import presence, repository, service
from app.modules.rooms.models import Room, RoomMember, RoomPresenceCount
from app.modules.rooms.schemas import JoinRoomResponse

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)


@pytest.fixture
def pg_room(pg_engine: Engine) -> UUID:
    now = datetime.now(UTC)
    with Session(pg_engine) as db:
        room = Room(
            id=uuid4(),
            name=f"Test Library {uuid4()}",
            description="Isolated PostgreSQL test room",
            category="library",
            latitude=29.65,
            longitude=-82.34,
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(room)
        db.flush()
        room_id = room.id
        db.commit()
    return room_id


def new_user(engine: Engine) -> UUID:
    user_id = uuid4()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO auth.users (id) VALUES (:id)"), {"id": user_id})
    return user_id


def join(engine: Engine, room_id: UUID, session_id: UUID) -> JoinRoomResponse:
    with Session(engine) as db:
        return service.join_room(db, str(session_id), room_id)


def leave(engine: Engine, room_id: UUID, session_id: UUID) -> None:
    with Session(engine) as db:
        service.leave_room(db, str(session_id), room_id)


def heartbeat(engine: Engine, room_id: UUID, session_id: UUID) -> None:
    with Session(engine) as db:
        service.heartbeat_room(db, str(session_id), room_id)


def wait_for_lock(engine: Engine, event: str) -> None:
    deadline = monotonic() + 5
    with engine.connect() as connection:
        while monotonic() < deadline:
            if connection.scalar(
                text(
                    "SELECT EXISTS (SELECT FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                    "AND wait_event = :event)"
                ),
                {"event": event},
            ):
                return
            # pg_stat_activity is cached per transaction; sample the next wait afresh.
            connection.rollback()
            sleep(0.01)
    pytest.fail(f"A competing transaction never waited for the {event} lock")


def test_migration_constraints_defaults_and_rls(pg_engine: Engine, pg_room: UUID) -> None:
    schema = inspect(pg_engine)
    assert schema.get_pk_constraint("room_members")["constrained_columns"] == [
        "room_id",
        "session_id",
    ]
    columns = {column["name"]: column for column in schema.get_columns("room_members")}
    assert set(columns) == {
        "room_id",
        "session_id",
        "nickname",
        "joined_at",
        "last_seen_at",
        "left_at",
    }
    assert {name for name, column in columns.items() if column["nullable"]} == {"left_at"}
    for name in ("joined_at", "last_seen_at", "left_at"):
        assert columns[name]["type"].timezone
    foreign_keys = schema.get_foreign_keys("room_members")
    assert {(fk["referred_schema"], fk["referred_table"]) for fk in foreign_keys} == {
        (None, "rooms"),
        ("auth", "users"),
    }
    user_id = new_user(pg_engine)
    with pg_engine.begin() as connection:
        timestamps = connection.execute(
            text(
                "INSERT INTO public.room_members (room_id, session_id, nickname) "
                "VALUES (:room, :user, 'Quiet Otter') RETURNING joined_at, last_seen_at, left_at"
            ),
            {"room": pg_room, "user": user_id},
        ).one()
        assert timestamps.joined_at == timestamps.last_seen_at
        assert timestamps.joined_at.tzinfo is not None
        assert timestamps.left_at is None
        assert connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.room_members'::regclass")
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policy "
                    "WHERE polrelid = 'public.room_members'::regclass"
                )
            )
            == 0
        )

    for room_id, session_id in ((pg_room, user_id), (uuid4(), user_id), (pg_room, uuid4())):
        with pytest.raises(IntegrityError), pg_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.room_members (room_id, session_id, nickname) "
                    "VALUES (:room, :user, 'Calm Fox')"
                ),
                {"room": room_id, "user": session_id},
            )


def test_deleting_auth_user_cascades_only_their_memberships(
    pg_engine: Engine, pg_room: UUID
) -> None:
    deleted_user = new_user(pg_engine)
    surviving_user = new_user(pg_engine)
    with pg_engine.begin() as connection:
        other_room = connection.scalar(
            text(
                "INSERT INTO public.rooms (name, description, category, latitude, longitude) "
                "VALUES (:name, 'Other room', 'library', 29.65, -82.34) RETURNING id"
            ),
            {"name": str(uuid4())},
        )
    for room_id in (pg_room, other_room):
        join(pg_engine, room_id, deleted_user)
        join(pg_engine, room_id, surviving_user)

    with pg_engine.begin() as connection:
        # Include historical membership in the cleanup, as well as active membership.
        connection.execute(
            update(RoomMember)
            .where(RoomMember.room_id == other_room, RoomMember.session_id == deleted_user)
            .values(left_at=NOW)
        )
        rooms_before = connection.execute(text("SELECT * FROM public.rooms ORDER BY id")).all()
        users_before = connection.execute(
            text("SELECT * FROM auth.users WHERE id <> :id ORDER BY id"), {"id": deleted_user}
        ).all()
        memberships_before = connection.execute(
            text(
                "SELECT * FROM public.room_members WHERE session_id <> :id "
                "ORDER BY room_id, session_id"
            ),
            {"id": deleted_user},
        ).all()
        assert (
            connection.scalar(
                text("SELECT count(*) FROM public.room_members WHERE session_id = :id"),
                {"id": deleted_user},
            )
            == 2
        )
        assert (
            connection.execute(
                text("DELETE FROM auth.users WHERE id = :id"), {"id": deleted_user}
            ).rowcount
            == 1
        )

    with pg_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM public.room_members WHERE session_id = :id"),
                {"id": deleted_user},
            )
            == 0
        )
        assert (
            connection.execute(text("SELECT * FROM public.rooms ORDER BY id")).all() == rooms_before
        )
        assert (
            connection.execute(text("SELECT * FROM auth.users ORDER BY id")).all() == users_before
        )
        assert (
            connection.execute(
                text("SELECT * FROM public.room_members ORDER BY room_id, session_id")
            ).all()
            == memberships_before
        )


@pytest.mark.parametrize(
    "age,reserved", [(30, True), (59, True), (60, True), (60.000001, False), (61, False)]
)
def test_postgres_reservation_boundary(
    pg_engine: Engine, pg_room: UUID, monkeypatch: pytest.MonkeyPatch, age: float, reserved: bool
) -> None:
    user_id = new_user(pg_engine)
    monkeypatch.setattr(service, "utc_now", lambda: NOW)
    with Session(pg_engine) as db:
        repository.upsert_member(db, pg_room, user_id, "Quiet Otter", NOW - timedelta(seconds=age))
        db.commit()
    monkeypatch.setattr(
        service,
        "generate_nickname",
        lambda taken: next(name for name in ("Quiet Otter", "Calm Fox") if name not in taken),
    )
    result = join(pg_engine, pg_room, user_id)
    assert result.nickname == ("Quiet Otter" if reserved else "Calm Fox")


@pytest.mark.parametrize("same_session", [False, True])
def test_concurrent_joins_serialize_per_room(
    pg_engine: Engine, pg_room: UUID, monkeypatch: pytest.MonkeyPatch, same_session: bool
) -> None:
    users = [new_user(pg_engine) for _ in range(3)]
    if same_session:
        users[1] = users[0]
    with pg_engine.begin() as connection:
        other_room = connection.scalar(
            text(
                "INSERT INTO public.rooms (name, description, category, latitude, longitude) "
                "VALUES (:name, 'Other room', 'library', 29.65, -82.34) RETURNING id"
            ),
            {"name": str(uuid4())},
        )
    generating = Event()
    release = Event()

    def choose(taken: set[str]) -> str:
        if not generating.is_set():
            generating.set()
            assert release.wait(10), "Test did not release the first join"
        return next(name for name in ("Quiet Otter", "Calm Fox") if name not in taken)

    monkeypatch.setattr(service, "generate_nickname", choose)
    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(join, pg_engine, pg_room, users[0])
        try:
            assert generating.wait(5)
            second = executor.submit(join, pg_engine, pg_room, users[1])
            wait_for_lock(pg_engine, "advisory")
            assert not second.done()
            # A join in another room must finish while this room's transaction is locked.
            other = executor.submit(join, pg_engine, other_room, users[2])
            assert other.result(timeout=5).nickname == "Quiet Otter"
        finally:
            release.set()
        assert first.result(timeout=5).nickname == "Quiet Otter"
        assert second.result(timeout=5).nickname == ("Quiet Otter" if same_session else "Calm Fox")
    with Session(pg_engine) as db:
        assert set(
            db.scalars(select(RoomMember.nickname).where(RoomMember.room_id == pg_room))
        ) == ({"Quiet Otter"} if same_session else {"Quiet Otter", "Calm Fox"})


def test_queued_join_samples_time_after_acquiring_lock(
    pg_engine: Engine, pg_room: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = new_user(pg_engine)
    current_time = [NOW]
    monkeypatch.setattr(service, "utc_now", lambda: current_time[0])
    monkeypatch.setattr(
        service,
        "generate_nickname",
        lambda taken: next(name for name in ("Quiet Otter", "Calm Fox") if name not in taken),
    )
    with Session(pg_engine) as blocker:
        repository.upsert_member(
            db=blocker,
            room_id=pg_room,
            session_id=user_id,
            nickname="Quiet Otter",
            now=NOW - timedelta(seconds=59),
        )
        blocker.commit()
        repository.lock_room(blocker, pg_room)
        with ThreadPoolExecutor(max_workers=1) as executor:
            queued = executor.submit(join, pg_engine, pg_room, user_id)
            try:
                wait_for_lock(pg_engine, "advisory")
                current_time[0] = NOW + timedelta(seconds=2)
            finally:
                blocker.commit()
            assert queued.result(timeout=5).nickname == "Calm Fox"


def test_rollback_releases_lock_and_membership_write(
    pg_engine: Engine, pg_room: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = new_user(pg_engine)
    original = repository.upsert_member

    def fail_after_flush(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("failure after membership write")

    monkeypatch.setattr(repository, "upsert_member", fail_after_flush)
    with pytest.raises(RuntimeError, match="after membership write"):
        join(pg_engine, pg_room, user_id)
    monkeypatch.setattr(repository, "upsert_member", original)
    with Session(pg_engine) as db:
        assert db.get(RoomMember, (pg_room, user_id)) is None
        # Another connection can take the same transaction lock immediately after rollback.
        assert db.scalar(
            select(text("pg_try_advisory_xact_lock(:key)")).params(
                key=repository.room_lock_key(pg_room)
            )
        )
    assert join(pg_engine, pg_room, user_id).nickname


@pytest.mark.parametrize("leave_first", [True, False])
def test_concurrent_heartbeat_cannot_revive_a_left_membership(
    pg_engine: Engine, pg_room: UUID, monkeypatch: pytest.MonkeyPatch, leave_first: bool
) -> None:
    user_id = new_user(pg_engine)
    monkeypatch.setattr(service, "utc_now", lambda: NOW - timedelta(seconds=15))
    join(pg_engine, pg_room, user_id)
    monkeypatch.setattr(service, "utc_now", lambda: NOW)
    writing, release = Event(), Event()
    operation = "leave" if leave_first else "heartbeat"
    original = getattr(repository, operation)

    def hold_write(*args, **kwargs):
        result = original(*args, **kwargs)
        writing.set()
        assert release.wait(10), "Test did not release the first membership update"
        return result

    monkeypatch.setattr(repository, operation, hold_write)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(leave if leave_first else heartbeat, pg_engine, pg_room, user_id)
        try:
            assert writing.wait(5)
            pending = executor.submit(
                heartbeat if leave_first else leave, pg_engine, pg_room, user_id
            )
            wait_for_lock(pg_engine, "advisory")
            assert not pending.done()
        finally:
            release.set()
        first.result(timeout=5)
        if leave_first:
            with pytest.raises(NotAMember):
                pending.result(timeout=5)
        else:
            pending.result(timeout=5)
    with Session(pg_engine) as db:
        member = db.get(RoomMember, (pg_room, user_id))
        assert member.left_at == NOW
        assert member.last_seen_at == (NOW - timedelta(seconds=15) if leave_first else NOW)
        assert (
            next(room for room in service.list_rooms(db) if room.id == pg_room).participant_count
            == 0
        )


@pytest.mark.parametrize("same_session", [False, True])
@pytest.mark.parametrize("leave_first", [False, True])
def test_leave_and_join_share_the_room_transaction_lock(
    pg_engine: Engine,
    pg_room: UUID,
    monkeypatch: pytest.MonkeyPatch,
    same_session: bool,
    leave_first: bool,
) -> None:
    user_id = new_user(pg_engine)
    joiner = user_id if same_session else new_user(pg_engine)
    current_time = [NOW]
    monkeypatch.setattr(service, "utc_now", lambda: current_time[0])
    monkeypatch.setattr(
        service,
        "generate_nickname",
        lambda taken: next(name for name in ("Quiet Otter", "Calm Fox") if name not in taken),
    )
    assert join(pg_engine, pg_room, user_id).nickname == "Quiet Otter"
    writing, release = Event(), Event()
    operation = "leave" if leave_first else "upsert_member"
    original = getattr(repository, operation)

    def hold_write(*args, **kwargs):
        result = original(*args, **kwargs)
        writing.set()
        assert release.wait(10), "Test did not release the first room transaction"
        return result

    monkeypatch.setattr(repository, operation, hold_write)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            leave if leave_first else join, pg_engine, pg_room, user_id if leave_first else joiner
        )
        try:
            assert writing.wait(5)
            pending = executor.submit(
                join if leave_first else leave,
                pg_engine,
                pg_room,
                joiner if leave_first else user_id,
            )
            wait_for_lock(pg_engine, "advisory")
            assert not pending.done()
            current_time[0] = NOW + timedelta(seconds=1)
        finally:
            release.set()
        first.result(timeout=5)
        result = pending.result(timeout=5)
        if leave_first:
            assert result.nickname == ("Calm Fox" if same_session else "Quiet Otter")
    with Session(pg_engine) as db:
        member = db.get(RoomMember, (pg_room, user_id))
        if leave_first and same_session:
            assert member.left_at is None
            assert member.last_seen_at == current_time[0]
        else:
            assert member.left_at == (NOW if leave_first else current_time[0])
        room = next(room for room in service.list_rooms(db) if room.id == pg_room)
        assert room.participant_count == (0 if same_session and not leave_first else 1)


@pytest.mark.parametrize(
    "age,left,expected",
    [
        (0, False, 1),
        (29.999999, False, 1),
        (30, False, 1),
        (30.000001, False, 0),
        (60, False, 0),
        (0, True, 0),
    ],
)
def test_postgres_presence_boundary_and_leave(
    pg_engine: Engine,
    pg_room: UUID,
    monkeypatch: pytest.MonkeyPatch,
    age: float,
    left: bool,
    expected: int,
) -> None:
    user_id = new_user(pg_engine)
    monkeypatch.setattr(service, "utc_now", lambda: NOW)
    with Session(pg_engine) as db:
        member = repository.upsert_member(
            db, pg_room, user_id, "Quiet Otter", NOW - timedelta(seconds=age)
        )
        if left:
            member.left_at = NOW
        db.commit()
        room = next(room for room in service.list_rooms(db) if room.id == pg_room)
        assert room.participant_count == expected
    if not left:
        leave(pg_engine, pg_room, user_id)
    with Session(pg_engine) as db:
        room = next(room for room in service.list_rooms(db) if room.id == pg_room)
        assert room.participant_count == 0


def test_postgres_leave_rollback_releases_lock(
    pg_engine: Engine, pg_room: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = new_user(pg_engine)
    join(pg_engine, pg_room, user_id)
    original = repository.leave

    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("failure after leave write")

    monkeypatch.setattr(repository, "leave", fail_after_write)
    with Session(pg_engine) as db:
        with pytest.raises(RuntimeError, match="after leave write"):
            service.leave_room(db, str(user_id), pg_room)
        assert not db.in_transaction()
        assert db.get(RoomMember, (pg_room, user_id)).left_at is None
    monkeypatch.setattr(repository, "leave", original)
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(leave, pg_engine, pg_room, user_id).result(timeout=5)


def test_postgres_leave_isolates_room_and_user(
    pg_engine: Engine, pg_room: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "utc_now", lambda: NOW)
    users = [new_user(pg_engine), new_user(pg_engine)]
    with pg_engine.begin() as connection:
        other_room = connection.scalar(
            text(
                "INSERT INTO public.rooms (name, description, category, latitude, longitude) "
                "VALUES (:name, 'Other room', 'library', 29.65, -82.34) RETURNING id"
            ),
            {"name": str(uuid4())},
        )
    for room_id in (pg_room, other_room):
        for user in users:
            join(pg_engine, room_id, user)
    query = select(RoomMember.__table__).where(RoomMember.room_id.in_([pg_room, other_room]))
    with Session(pg_engine) as db:
        before = {
            (row["room_id"], row["session_id"]): dict(row) for row in db.execute(query).mappings()
        }
        assert all(
            room.participant_count == 2
            for room in service.list_rooms(db)
            if room.id in (pg_room, other_room)
        )
    leave(pg_engine, pg_room, users[0])
    before[(pg_room, users[0])]["left_at"] = NOW
    with Session(pg_engine) as db:
        after = {
            (row["room_id"], row["session_id"]): dict(row) for row in db.execute(query).mappings()
        }
        assert after == before
        counts = {room.id: room.participant_count for room in service.list_rooms(db)}
        assert counts[pg_room] == 1
        assert counts[other_room] == 2


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_cannot_access_memberships(
    pg_engine: Engine, pg_room: UUID, role: str
) -> None:
    user_id = new_user(pg_engine)
    join(pg_engine, pg_room, user_id)
    with pg_engine.connect() as connection:
        connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
        assert connection.execute(text("SELECT * FROM public.room_members")).all() == []
        assert (
            connection.execute(
                text("UPDATE public.room_members SET nickname = 'Forbidden'")
            ).rowcount
            == 0
        )
        assert connection.execute(text("DELETE FROM public.room_members")).rowcount == 0
        with pytest.raises(DBAPIError) as error:
            connection.execute(
                text(
                    "INSERT INTO public.room_members (room_id, session_id, nickname) "
                    "VALUES (:room, :user, 'Forbidden')"
                ),
                {"room": pg_room, "user": user_id},
            )
        assert error.value.orig.sqlstate == "42501"


def sweep(engine: Engine, room_id: UUID, session_id: UUID) -> None:
    with Session(engine) as db:
        service.sweep_room_presence(db, room_id)


def test_count_events_see_committed_data_and_released_room_lock(
    pg_engine: Engine, pg_room: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = new_user(pg_engine)
    monkeypatch.setattr(service, "utc_now", lambda: NOW)
    events = []

    def record(topic, event, payload):
        with Session(pg_engine) as db:
            # This connection must be able to take the lock while publishing is in
            # progress, and see the membership and snapshot committed together.
            assert db.scalar(
                select(text("pg_try_advisory_xact_lock(:key)")).params(
                    key=repository.room_lock_key(pg_room)
                )
            )
            count = repository.participant_count(db, pg_room, service.presence_since(NOW))
            assert db.get(RoomPresenceCount, pg_room).participant_count == count
            assert payload["count"] == count
        events.append((topic, event, payload))

    monkeypatch.setattr(presence, "publish", record)
    join(pg_engine, pg_room, user_id)
    join(pg_engine, pg_room, user_id)
    heartbeat(pg_engine, pg_room, user_id)
    leave(pg_engine, pg_room, user_id)
    assert events == [
        (f"room:{pg_room}", "presence.updated", {"count": 1}),
        ("rooms", "room.count", {"room_id": str(pg_room), "count": 1}),
        (f"room:{pg_room}", "presence.updated", {"count": 0}),
        ("rooms", "room.count", {"room_id": str(pg_room), "count": 0}),
    ]


@pytest.mark.parametrize("operation", ["join", "heartbeat", "leave", "sweep"])
@pytest.mark.parametrize("sweep_first", [False, True])
def test_sweeper_serializes_with_membership_activity(
    pg_engine: Engine,
    pg_room: UUID,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    sweep_first: bool,
) -> None:
    user_id = new_user(pg_engine)
    clock = [NOW]
    monkeypatch.setattr(service, "utc_now", lambda: clock[0])
    join(pg_engine, pg_room, user_id)
    clock[0] += timedelta(seconds=31)
    events = []
    monkeypatch.setattr(presence, "publish", lambda *event: events.append(event))
    writing, release = Event(), Event()
    original = repository.refresh_presence_count

    def hold_observation(*args, **kwargs):
        result = original(*args, **kwargs)
        if not writing.is_set():
            writing.set()
            assert release.wait(10), "Test did not release the first presence observation"
        return result

    monkeypatch.setattr(repository, "refresh_presence_count", hold_observation)
    competing = {"join": join, "heartbeat": heartbeat, "leave": leave, "sweep": sweep}[operation]
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(sweep if sweep_first else competing, pg_engine, pg_room, user_id)
        try:
            assert writing.wait(5)
            second = executor.submit(
                competing if sweep_first else sweep, pg_engine, pg_room, user_id
            )
            wait_for_lock(pg_engine, "advisory")
            assert not second.done()
            clock[0] += timedelta(seconds=1)
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)

    expected = [0] if operation in {"leave", "sweep"} else ([0, 1] if sweep_first else [])
    for topic, event_name in ((f"room:{pg_room}", "presence.updated"), ("rooms", "room.count")):
        payloads = [
            payload for channel, name, payload in events if (channel, name) == (topic, event_name)
        ]
        assert sorted(payload["count"] for payload in payloads) == expected
        for payload in payloads:
            assert set(payload) == (
                {"count"} if event_name == "presence.updated" else {"room_id", "count"}
            )
    assert len(events) == 2 * len(expected)
    with Session(pg_engine) as db:
        count = repository.participant_count(db, pg_room, service.presence_since(clock[0]))
        assert count == (0 if operation in {"leave", "sweep"} else 1)
        assert db.get(RoomPresenceCount, pg_room).participant_count == count
        member = db.get(RoomMember, (pg_room, user_id))
        assert (member.left_at is not None) == (operation == "leave")
        if operation == "heartbeat":
            assert member.last_seen_at == (clock[0] if sweep_first else NOW + timedelta(seconds=31))
    # A fresh session must not repeat any timeout consumed by either transaction.
    events.clear()
    sweep(pg_engine, pg_room, user_id)
    assert events == []


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_presence_snapshot_migration_constraints_and_rls(
    pg_engine: Engine, pg_room: UUID, role: str
) -> None:
    schema = inspect(pg_engine)
    assert schema.get_pk_constraint("room_presence_counts")["constrained_columns"] == ["room_id"]
    foreign_key = schema.get_foreign_keys("room_presence_counts")[0]
    assert foreign_key["referred_table"] == "rooms"
    assert foreign_key["options"]["ondelete"] == "CASCADE"
    user_id = new_user(pg_engine)
    join(pg_engine, pg_room, user_id)
    with pg_engine.begin() as connection:
        assert connection.scalar(
            text(
                "SELECT relrowsecurity FROM pg_class "
                "WHERE oid = 'public.room_presence_counts'::regclass"
            )
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policy "
                    "WHERE polrelid = 'public.room_presence_counts'::regclass"
                )
            )
            == 0
        )
    with pytest.raises(IntegrityError), pg_engine.begin() as connection:
        connection.exec_driver_sql("UPDATE public.room_presence_counts SET participant_count = -1")
    with pg_engine.connect() as connection:
        connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
        assert connection.execute(text("SELECT * FROM public.room_presence_counts")).all() == []
        assert (
            connection.execute(
                text("UPDATE public.room_presence_counts SET participant_count = 0")
            ).rowcount
            == 0
        )
        assert connection.execute(text("DELETE FROM public.room_presence_counts")).rowcount == 0
        with pytest.raises(DBAPIError) as error:
            connection.execute(
                text(
                    "INSERT INTO public.room_presence_counts (room_id, participant_count) "
                    "VALUES (:room, 0)"
                ),
                {"room": pg_room},
            )
        assert error.value.orig.sqlstate == "42501"


@pytest.mark.parametrize("fail_first_publish", [False, True])
def test_slow_publisher_preserves_order_without_holding_database_locks(
    pg_engine: Engine,
    pg_room: UUID,
    monkeypatch: pytest.MonkeyPatch,
    fail_first_publish: bool,
) -> None:
    users = [new_user(pg_engine) for _ in range(3)]
    with pg_engine.begin() as connection:
        other_room = connection.scalar(
            text(
                "INSERT INTO public.rooms (name, description, category, latitude, longitude) "
                "VALUES (:name, 'Other room', 'library', 29.65, -82.34) RETURNING id"
            ),
            {"name": str(uuid4())},
        )
    monkeypatch.setattr(service, "utc_now", lambda: NOW)
    publishing, release, second_committed = Event(), Event(), Event()
    events = []

    def record(topic, name, payload):
        if topic == f"room:{pg_room}" and payload["count"] == 1:
            publishing.set()
            assert release.wait(10), "Test did not release the first publisher"
            if fail_first_publish:
                raise RuntimeError("test first-channel failure")
        events.append((topic, name, payload))

    def second_join():
        with Session(pg_engine) as db:
            event.listen(db, "after_commit", lambda session: second_committed.set())
            return service.join_room(db, str(users[1]), pg_room)

    monkeypatch.setattr(presence, "publish", record)
    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(join, pg_engine, pg_room, users[0])
        try:
            assert publishing.wait(5)
            second = executor.submit(second_join)
            assert second_committed.wait(5), "A slow publisher blocked the next transaction"
            assert not second.done()
            other = executor.submit(join, pg_engine, other_room, users[2])
            assert other.result(timeout=5).nickname
            with Session(pg_engine) as db:
                assert db.scalar(
                    select(text("pg_try_advisory_xact_lock(:key)")).params(
                        key=repository.room_lock_key(pg_room)
                    )
                )
                assert db.get(RoomPresenceCount, pg_room).participant_count == 2
                assert repository.participant_count(db, pg_room, service.presence_since(NOW)) == 2
        finally:
            release.set()
        assert first.result(timeout=5).nickname
        assert second.result(timeout=5).nickname
    events = [
        item
        for item in events
        if item[0] == f"room:{pg_room}" or item[2].get("room_id") == str(pg_room)
    ]
    expected = [
        (f"room:{pg_room}", "presence.updated", {"count": 1}),
        ("rooms", "room.count", {"room_id": str(pg_room), "count": 1}),
        (f"room:{pg_room}", "presence.updated", {"count": 2}),
        ("rooms", "room.count", {"room_id": str(pg_room), "count": 2}),
    ]
    assert events == (expected[1:] if fail_first_publish else expected)
