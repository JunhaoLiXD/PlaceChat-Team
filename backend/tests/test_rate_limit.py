from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.db import Base
from app.core.errors import RateLimited
from app.modules.messaging.models import Message
from app.modules.safety import rate_limit


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> datetime:
    now = datetime(2026, 10, 23, 17, 0, tzinfo=UTC)
    monkeypatch.setattr(rate_limit, "utc_now", lambda: now)
    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            rate_limit_max_messages=5,
            rate_limit_window_seconds=10,
        ),
    )
    return now


def add_message(db: Session, session_id: str, room_id: str, created_at: datetime) -> None:
    db.add(
        Message(
            id=uuid4(),
            room_id=UUID(room_id),
            session_id=UUID(session_id),
            nickname="Quiet Otter",
            body="hello",
            created_at=created_at,
        )
    )
    db.flush()


def test_five_messages_are_allowed(db: Session, clock: datetime) -> None:
    session_id = str(uuid4())
    for offset in range(5):
        rate_limit.check_rate_limit(db, session_id)
        add_message(db, session_id, str(uuid4()), clock - timedelta(seconds=offset))


def test_sixth_message_is_blocked_with_rounded_retry_after(db: Session, clock: datetime) -> None:
    session_id = str(uuid4())
    for offset in range(5):
        created_at = clock - timedelta(seconds=offset, milliseconds=200)
        add_message(db, session_id, str(uuid4()), created_at)

    with pytest.raises(RateLimited) as caught:
        rate_limit.check_rate_limit(db, session_id)

    assert caught.value.extra["retry_after"] == 6
    assert "sending messages too fast" in caught.value.message


def test_limit_allows_sending_after_window(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = str(uuid4())
    sent_at = datetime(2026, 10, 23, 16, 59, 59, tzinfo=UTC)
    add_message(db, session_id, str(uuid4()), sent_at)
    for _ in range(4):
        add_message(db, session_id, str(uuid4()), sent_at + timedelta(seconds=1))

    monkeypatch.setattr(rate_limit, "utc_now", lambda: sent_at + timedelta(seconds=11))
    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: Settings(_env_file=None, rate_limit_max_messages=5, rate_limit_window_seconds=10),
    )

    rate_limit.check_rate_limit(db, session_id)


def test_limit_is_shared_across_rooms(db: Session, clock: datetime) -> None:
    session_id = str(uuid4())
    for _ in range(5):
        add_message(db, session_id, str(uuid4()), clock)

    with pytest.raises(RateLimited):
        rate_limit.check_rate_limit(db, session_id)
