"""Administrator allow-list migration, authorization, and RLS on disposable PostgreSQL."""

from uuid import uuid4

import pytest
from sqlalchemy import Engine, Uuid, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import Admin, require_admin
from app.core.auth import Session as Identity
from app.core.errors import Forbidden


def test_admin_migration_constraints_defaults_and_rls(pg_engine: Engine) -> None:
    schema = inspect(pg_engine)
    assert schema.get_pk_constraint("admin_users")["constrained_columns"] == ["user_id"]
    columns = {column["name"]: column for column in schema.get_columns("admin_users")}
    assert set(columns) == {"user_id", "display_name", "created_at"}
    assert not any(column["nullable"] for column in columns.values())
    assert isinstance(columns["user_id"]["type"], Uuid)
    assert columns["created_at"]["type"].timezone
    (foreign_key,) = schema.get_foreign_keys("admin_users")
    assert (foreign_key["referred_schema"], foreign_key["referred_table"]) == ("auth", "users")
    assert foreign_key["options"]["ondelete"] == "CASCADE"
    user_id = uuid4()
    with pg_engine.begin() as connection:
        assert connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.admin_users'::regclass")
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policy WHERE polrelid = 'public.admin_users'::regclass"
                )
            )
            == 0
        )
        connection.execute(text("INSERT INTO auth.users (id) VALUES (:id)"), {"id": user_id})
        created = connection.scalar(
            text(
                "INSERT INTO public.admin_users (user_id, display_name) "
                "VALUES (:id, 'Synthetic admin') RETURNING created_at"
            ),
            {"id": user_id},
        )
        assert created.tzinfo is not None

    unnamed_user = uuid4()
    with pg_engine.begin() as connection:
        connection.execute(text("INSERT INTO auth.users (id) VALUES (:id)"), {"id": unnamed_user})
    for target, name, sqlstate in (
        (user_id, "Duplicate", "23505"),
        (uuid4(), "Orphan", "23503"),
        (unnamed_user, None, "23502"),
    ):
        with pytest.raises(IntegrityError) as error, pg_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO public.admin_users (user_id, display_name) VALUES (:id, :name)"),
                {"id": target, "name": name},
            )
        assert error.value.orig.sqlstate == sqlstate

    with pg_engine.begin() as connection:
        connection.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": user_id})
        assert (
            connection.scalar(
                text("SELECT count(*) FROM public.admin_users WHERE user_id = :id"), {"id": user_id}
            )
            == 0
        )


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_browser_roles_cannot_read_or_grant_admin_privileges(pg_engine: Engine, role: str) -> None:
    user_id = uuid4()
    with pg_engine.begin() as connection:
        connection.execute(text("INSERT INTO auth.users (id) VALUES (:id)"), {"id": user_id})
        connection.execute(
            text("INSERT INTO public.admin_users (user_id, display_name) VALUES (:id, 'Existing')"),
            {"id": user_id},
        )
    with pg_engine.connect() as connection:
        connection.exec_driver_sql(f"SET LOCAL ROLE {role}")
        assert connection.execute(text("SELECT * FROM public.admin_users")).all() == []
        assert (
            connection.execute(
                text("UPDATE public.admin_users SET display_name = 'Forbidden'")
            ).rowcount
            == 0
        )
        assert connection.execute(text("DELETE FROM public.admin_users")).rowcount == 0
        with pytest.raises(DBAPIError) as error:
            connection.execute(
                text("INSERT INTO public.admin_users (user_id, display_name) VALUES (:id, 'Self')"),
                {"id": user_id},
            )
        assert error.value.orig.sqlstate == "42501"
    with pg_engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT display_name FROM public.admin_users WHERE user_id = :id"),
                {"id": user_id},
            )
            == "Existing"
        )


@pytest.mark.parametrize(
    "anonymous,listed", [(True, False), (True, True), (False, False), (False, True)]
)
def test_require_admin_uses_postgres_allow_list(
    pg_engine: Engine, anonymous: bool, listed: bool
) -> None:
    user_id = uuid4()
    with pg_engine.begin() as connection:
        connection.execute(text("INSERT INTO auth.users (id) VALUES (:id)"), {"id": user_id})
        if listed:
            connection.execute(
                text(
                    "INSERT INTO public.admin_users (user_id, display_name) VALUES (:id, 'Admin')"
                ),
                {"id": user_id},
            )
    with Session(pg_engine) as db:
        identity = Identity(id=str(user_id), is_anonymous=anonymous)
        if listed and not anonymous:
            assert require_admin(identity, db) == Admin(user_id=str(user_id))
        else:
            with pytest.raises(Forbidden):
                require_admin(identity, db)
