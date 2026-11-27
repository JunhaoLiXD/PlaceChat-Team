"""Actual block migration defaults, constraints, index, and RLS on disposable PostgreSQL."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, Uuid, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError


def test_blocks_migration_defaults_constraints_and_index(pg_engine: Engine) -> None:
    schema = inspect(pg_engine)
    assert schema.get_pk_constraint("blocks")["constrained_columns"] == ["id"]
    columns = {column["name"]: column for column in schema.get_columns("blocks")}
    assert set(columns) == {"id", "session_id", "reason", "created_by", "created_at", "expires_at"}
    assert {name for name, column in columns.items() if column["nullable"]} == {"reason"}
    for name in ("id", "session_id", "created_by"):
        assert isinstance(columns[name]["type"], Uuid)
    for name in ("created_at", "expires_at"):
        assert columns[name]["type"].timezone
    assert any(
        index["column_names"] == ["session_id", "expires_at"]
        for index in schema.get_indexes("blocks")
    )
    with pg_engine.begin() as connection:
        assert connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.blocks'::regclass")
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM pg_policy WHERE polrelid = 'public.blocks'::regclass")
            )
            == 0
        )
        row = connection.execute(
            text(
                "INSERT INTO public.blocks (session_id, created_by, expires_at) "
                "VALUES (:sender, :admin, now() + interval '15 minutes') "
                "RETURNING id, reason, created_at, expires_at"
            ),
            {"sender": uuid4(), "admin": uuid4()},
        ).one()
        assert row.id and row.reason is None
        assert row.created_at.tzinfo is not None
        assert row.expires_at - row.created_at == timedelta(minutes=15)

    for minutes in (-1, 0):
        with pytest.raises(IntegrityError) as error, pg_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO public.blocks (session_id, created_by, expires_at) "
                    "VALUES (:sender, :admin, now() + make_interval(mins => :minutes))"
                ),
                {"sender": uuid4(), "admin": uuid4(), "minutes": minutes},
            )
        assert error.value.orig.sqlstate == "23514"


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_cannot_read_change_or_create_blocks(pg_engine: Engine, role: str) -> None:
    session_id, admin_id = uuid4(), uuid4()
    until = datetime.now(UTC) + timedelta(hours=1)
    with pg_engine.begin() as connection:
        connection.exec_driver_sql(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON public.blocks TO anon, authenticated"
        )
        block_id = connection.scalar(
            text(
                "INSERT INTO public.blocks (session_id, created_by, expires_at) "
                "VALUES (:sender, :admin, :until) RETURNING id"
            ),
            {"sender": session_id, "admin": admin_id, "until": until},
        )
    with pg_engine.connect() as connection:
        connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
        assert connection.execute(text("SELECT * FROM public.blocks")).all() == []
        assert (
            connection.execute(text("UPDATE public.blocks SET reason = 'Forbidden'")).rowcount == 0
        )
        assert connection.execute(text("DELETE FROM public.blocks")).rowcount == 0
        with pytest.raises(DBAPIError) as error:
            connection.execute(
                text(
                    "INSERT INTO public.blocks (session_id, created_by, expires_at) "
                    "VALUES (:sender, :admin, :until)"
                ),
                {"sender": session_id, "admin": admin_id, "until": until},
            )
        assert error.value.orig.sqlstate == "42501"
    with pg_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT expires_at FROM public.blocks WHERE id = :id"), {"id": block_id}
            )
            == until
        )
