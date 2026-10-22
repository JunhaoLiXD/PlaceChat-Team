"""Real migrations, locks, and RLS on a disposable, loopback-only PostgreSQL database.

Set TEST_DATABASE_URL to a local placechat_pbi07_* database on a disposable server.
The fixture creates and drops its own database; it never reads the application's DATABASE_URL.
Only auth.users' UUID key is stubbed: full Supabase Auth remains a live smoke check.
"""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.db import normalize_database_url
from app.core.errors import NotAMember
from app.modules.rooms import repository, service
from app.modules.rooms.models import Room, RoomMember
from app.modules.rooms.schemas import JoinRoomResponse

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)
MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"


@pytest.fixture(scope="module")
def pg_engine() -> Iterator[Engine]:
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("Set TEST_DATABASE_URL to run isolated PostgreSQL membership checks")
    url = make_url(normalize_database_url(value))
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not (url.database or "").startswith("placechat_pbi07_")
        or url.query
    ):
        pytest.fail("Membership PostgreSQL tests require a loopback placechat_pbi07_* URL")

    # Never reset the supplied database. Each test run owns a new database by UUID.
    database = f"placechat_pbi07_{uuid4().hex}"
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    engine = create_engine(url.set(database=database), hide_parameters=True)
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE SCHEMA auth")
            connection.exec_driver_sql("CREATE TABLE auth.users (id uuid PRIMARY KEY)")
            for role in ("anon", "authenticated"):
                exists = connection.scalar(
                    text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = :role)"),
                    {"role": role},
                )
                if not exists:
                    connection.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN NOBYPASSRLS")
                assert connection.scalar(
                    text("SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname=:r"),
                    {"r": role},
                ), "Browser test roles must not bypass RLS"
            for migration in (
                "20261014180036_create_rooms.sql",
                "20261015201410_create_room_members.sql",
            ):
                connection.exec_driver_sql((MIGRATIONS / migration).read_text(encoding="utf-8"))
            # Exercise RLS itself, even when ordinary table privileges are granted.
            connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO anon, authenticated")
            connection.exec_driver_sql(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON public.room_members TO anon, authenticated"
            )
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database}"')
        admin.dispose()


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


@pytest.mark.parametrize("age,reserved", [(30, True), (60, True), (60.000001, False)])
def test_postgres_reservation_boundary(
    pg_engine: Engine, pg_room: UUID, monkeypatch: pytest.MonkeyPatch, age: float, reserved: bool
) -> None:
    user_id = new_user(pg_engine)
    monkeypatch.setattr(service, "utc_now", lambda: NOW)
    with Session(pg_engine) as db:
        repository.upsert_member(db, pg_room, user_id, "Quiet Otter", NOW - timedelta(seconds=age))
        db.commit()
    monkeypatch.setattr(service, "generate_nickname", lambda taken: "Calm Fox")
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
    monkeypatch.setattr(service, "generate_nickname", lambda taken: "Calm Fox")
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


def test_concurrent_heartbeat_cannot_revive_a_left_membership(
    pg_engine: Engine, pg_room: UUID
) -> None:
    user_id = new_user(pg_engine)
    join(pg_engine, pg_room, user_id)
    left_at = datetime.now(UTC)

    def heartbeat() -> None:
        with Session(pg_engine) as db:
            service.heartbeat_room(db, str(user_id), pg_room)

    with Session(pg_engine) as leaving:
        before = leaving.get(RoomMember, (pg_room, user_id)).last_seen_at
        leaving.execute(
            update(RoomMember).where(RoomMember.room_id == pg_room).values(left_at=left_at)
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(heartbeat)
            try:
                wait_for_lock(pg_engine, "transactionid")
            finally:
                leaving.commit()
            with pytest.raises(NotAMember):
                pending.result(timeout=5)
    with Session(pg_engine) as db:
        member = db.get(RoomMember, (pg_room, user_id))
        assert member.left_at == left_at
        assert member.last_seen_at == before


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
