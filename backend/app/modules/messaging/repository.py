"""Data access for messages. Owner: Junhao — PBI-14 (#18)."""

from sqlalchemy.orm import Session

from app.modules.messaging.models import Message


def add_message(db: Session, message: Message) -> None:
    db.add(message)
