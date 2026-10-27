"""The Message mapping shares the core Base with Room and round-trips through a test database."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.db import Base
from app.modules.messaging.models import Message
from app.modules.rooms.models import Room


def test_messages_table_references_rooms() -> None:
    messages = Base.metadata.tables["messages"]

    assert messages is Message.__table__
    assert [fk.target_fullname for fk in messages.foreign_keys] == ["rooms.id"]


def test_message_round_trip() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    room = Room(
        id=uuid4(),
        name="Library West",
        description="Test room description",
        category="library",
        latitude=29.65,
        longitude=-82.34,
        status="active",
        created_at=now,
        updated_at=now,
    )
    message = Message(
        id=uuid4(),
        room_id=room.id,
        session_id=uuid4(),
        nickname="Quiet Otter",
        body="hello",
        created_at=now,
    )

    with Session(engine) as db:
        db.add_all([room, message])
        db.commit()
        stored = db.scalars(select(Message)).one()

        assert (stored.room_id, stored.nickname, stored.body) == (room.id, "Quiet Otter", "hello")
        assert stored.removed_at is None and stored.removed_by is None
    engine.dispose()
