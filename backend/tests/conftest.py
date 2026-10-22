import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from app.core import realtime
from app.core.db import normalize_database_url
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def no_real_broadcasts(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A developer's backend/.env may hold staging keys; tests must never broadcast for real."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"test tried to call Realtime: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(refuse))
    monkeypatch.setattr(realtime, "get_http_client", lambda: client)
    yield
    client.close()


@pytest.fixture(scope="module")
def pg_engine() -> Iterator[Engine]:
    """Apply real migrations in a disposable local database, never the application database."""
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("Set TEST_DATABASE_URL to run isolated PostgreSQL checks")
    url = make_url(normalize_database_url(value))
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost", "::1"}
        or not (url.database or "").startswith("placechat_pbi07_")
        or url.query
    ):
        pytest.fail(
            "PostgreSQL tests require a loopback placechat_pbi07_* URL without query params"
        )

    # Never reset the supplied database. Each test module owns a new database by UUID.
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
            migrations = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
            for migration in (
                "20261014180036_create_rooms.sql",
                "20261015201410_create_room_members.sql",
                "20261021192836_create_admin_users.sql",
            ):
                connection.exec_driver_sql((migrations / migration).read_text(encoding="utf-8"))
            # Exercise RLS itself, even when ordinary table privileges are granted.
            connection.exec_driver_sql("GRANT USAGE ON SCHEMA public TO anon, authenticated")
            connection.exec_driver_sql(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON public.room_members, public.admin_users "
                "TO anon, authenticated"
            )
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{database}"')
        admin.dispose()
