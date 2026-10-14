from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.rooms.models import Room


def list_active_rooms(db: Session) -> list[Room]:
    return list(db.scalars(select(Room).where(Room.status == "active").order_by(Room.name)))
