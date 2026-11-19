"""Data access for admin room management. Owner: Junhao — PBI-22 (#26)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.rooms.models import Room


def get_room(db: Session, room_id: UUID) -> Room | None:
    return db.get(Room, room_id)


def list_rooms(db: Session) -> list[Room]:
    """Return every room for administration, including archived rooms."""
    query = select(Room).order_by(Room.name)
    return list(db.scalars(query))


def name_taken(db: Session, name: str, exclude_id: UUID | None = None) -> bool:
    """Case-insensitive, and archived rooms still hold their names (the column is unique)."""
    query = select(Room.id).where(func.lower(Room.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Room.id != exclude_id)
    return db.scalar(query.limit(1)) is not None


def add_room(db: Session, room: Room) -> None:
    db.add(room)
