"""Room membership contract (PlaceChat Technical Design §3.4, §5.2).

Owner: Zhijie — PBI-07 (#11).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session as DbSession

from app.modules.rooms import repository
from app.modules.rooms.schemas import RoomResponse


def list_rooms(db: DbSession) -> list[RoomResponse]:
    """List active rooms; counts stay zero until membership is implemented."""
    return [RoomResponse.model_validate(room) for room in repository.list_active_rooms(db)]


@dataclass(frozen=True)
class Membership:
    room_id: str
    session_id: str
    nickname: str
    joined_at: datetime


def ensure_member(db: DbSession, session_id: str, room_id: str) -> Membership:
    """Return the caller's membership in an active room.

    Raises RoomNotFound (404) if the room is missing or archived, NotAMember (403) if the caller
    has not joined it.
    """
    raise NotImplementedError("ensure_member is implemented in PBI-07 (#11)")
