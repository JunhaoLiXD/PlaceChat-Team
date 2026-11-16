"""Data access for messages. Owner: Junhao — PBI-14 (#18)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.modules.messaging.models import Message


def add_message(db: Session, message: Message) -> None:
    db.add(message)


def get_recent_messages(
    db: Session,
    room_id: UUID,
    limit: int,
    *,
    created_after: datetime | None = None,
    after: Message | None = None,
) -> list[Message]:
    """Return visible messages in chronological order, capped after newest selection."""
    query = select(Message).where(
        Message.room_id == room_id,
        Message.removed_at.is_(None),
    )
    if created_after is not None:
        query = query.where(Message.created_at >= created_after)
    if after is not None:
        query = query.where(
            or_(
                Message.created_at > after.created_at,
                and_(Message.created_at == after.created_at, Message.id > after.id),
            )
        )

    newest = query.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
    return list(reversed(list(db.scalars(newest))))


def get_message(db: Session, room_id: UUID, message_id: UUID) -> Message | None:
    return db.scalar(select(Message).where(Message.id == message_id, Message.room_id == room_id))
