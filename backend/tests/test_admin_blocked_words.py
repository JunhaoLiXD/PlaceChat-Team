"""Admin blocked-word routes against an isolated SQLite database.

The admin check is overridden; the last tests cover every /api/v1/admin route.
"""

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import Admin, require_admin
from app.core.config import get_settings
from app.core.db import Base, get_db
from app.core.errors import Forbidden, Unauthenticated
from app.main import create_app
from app.modules.safety import blocked_words
from app.modules.safety.models import BlockedWord
from app.modules.safety.word_filter import filter_text

PATH = "/api/v1/admin/blocked-words"


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
def app(db: Session) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_admin] = lambda: Admin(user_id="admin-1")
    return app


@pytest.fixture
def admin(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def add(admin: TestClient, word: str) -> Any:
    return admin.post(PATH, json={"word": word})


def words(admin: TestClient) -> list[str]:
    response = admin.get(PATH)
    assert response.status_code == 200
    return [item["word"] for item in response.json()]


def test_list_starts_empty_and_is_sorted(admin: TestClient) -> None:
    assert words(admin) == []
    add(admin, "zebra")
    add(admin, "apple")
    assert words(admin) == ["apple", "zebra"]


def test_add_trims_and_lowercases(admin: TestClient) -> None:
    response = add(admin, "  BadWord  ")

    assert response.status_code == 201
    body = response.json()
    assert body["word"] == "badword"
    assert set(body) == {"id", "word", "created_at"}
    assert words(admin) == ["badword"]


@pytest.mark.parametrize("spelling", ["badword", "BADWORD", " BadWord "])
def test_add_rejects_a_word_already_on_the_list(admin: TestClient, spelling: str) -> None:
    add(admin, "badword")

    response = add(admin, spelling)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert words(admin) == ["badword"]


@pytest.mark.parametrize(
    "payload",
    [
        {"word": ""},
        {"word": "   "},
        {"word": "x" * (get_settings().message_max_length + 1)},
        {"word": "ok", "extra": 1},
        {},
    ],
)
def test_add_rejects_invalid_input(admin: TestClient, payload: dict[str, Any]) -> None:
    response = admin.post(PATH, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert words(admin) == []


def test_add_lost_race_is_reported_as_duplicate(
    admin: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another admin's insert lands between our check and our commit.
    real_exists = blocked_words._exists
    calls = {"count": 0}

    def exists_after_race(session: Session, word: str) -> bool:
        calls["count"] += 1
        if calls["count"] == 1:
            session.add(
                BlockedWord(
                    id=blocked_words.uuid4(),
                    word=word,
                    created_at=blocked_words.datetime.now(blocked_words.UTC),
                )
            )
            session.commit()
            return False
        return real_exists(session, word)

    monkeypatch.setattr(blocked_words, "_exists", exists_after_race)

    response = add(admin, "badword")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert db.scalars(select(BlockedWord.word)).all() == ["badword"]


def test_delete_removes_the_word_and_repeating_it_is_fine(admin: TestClient) -> None:
    word_id = add(admin, "badword").json()["id"]

    assert admin.delete(f"{PATH}/{word_id}").status_code == 204
    assert words(admin) == []
    assert admin.delete(f"{PATH}/{word_id}").status_code == 204


def test_a_new_word_applies_to_the_next_message(admin: TestClient, db: Session) -> None:
    text = "That was a BadWord, honestly."
    assert filter_text(db, text) == text

    word_id = add(admin, "badword").json()["id"]
    assert filter_text(db, text) == "That was a *******, honestly."

    admin.delete(f"{PATH}/{word_id}")
    assert filter_text(db, text) == text


def test_every_admin_route_requires_admin(app: FastAPI, db: Session) -> None:
    """Safety net: every route under /api/v1/admin, now and later, rejects non-admins."""
    paths = {p: ops for p, ops in app.openapi()["paths"].items() if p.startswith("/api/v1/admin")}
    assert {PATH, f"{PATH}/{{word_id}}", "/api/v1/admin/rooms", "/api/v1/admin/reports"} <= set(
        paths
    )

    def reject() -> Admin:
        raise Forbidden()

    app.dependency_overrides[require_admin] = reject
    zero = "00000000-0000-0000-0000-000000000000"
    with TestClient(app) as client:
        for path, operations in paths.items():
            url = re.sub(r"\{[^}]+\}", zero, path)
            for method in operations:
                response = client.request(method.upper(), url, json={})
                assert response.status_code == 403, f"{method.upper()} {path}"
                assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (Unauthenticated, 401, "UNAUTHENTICATED"),
        (Forbidden, 403, "FORBIDDEN"),
    ],
)
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", PATH, None),
        ("POST", PATH, {"word": "badword"}),
        ("DELETE", f"{PATH}/00000000-0000-0000-0000-000000000000", None),
    ],
)
def test_non_admins_are_rejected(
    app: FastAPI,
    db: Session,
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
    assert db.scalars(select(BlockedWord)).all() == []
