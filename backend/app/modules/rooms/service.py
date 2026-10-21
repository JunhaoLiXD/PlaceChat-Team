"""Room membership contract (PlaceChat Technical Design §3.4, §5.2).

Owner: Zhijie — PBI-07 (#11).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.errors import NotAMember, RoomNotFound
from app.modules.nicknames.service import generate_nickname
from app.modules.rooms import repository
from app.modules.rooms.schemas import JoinedRoom, JoinRoomResponse, RoomResponse


def list_rooms(db: DbSession) -> list[RoomResponse]:
    """List active rooms; live participant counts remain separate presence work."""
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
    room_uuid = _room_uuid(room_id)
    if repository.get_active_room(db, room_uuid) is None:
        raise RoomNotFound()
    member = repository.get_member(db, room_uuid, _session_uuid(session_id))
    if member is None or member.left_at is not None:
        raise NotAMember()
    # Membership is not presence: neither the 30s presence nor 60s hold cutoff
    # revokes a joined membership. Explicit Leave is a separate operation.
    return Membership(
        room_id=str(member.room_id),
        session_id=str(member.session_id),
        nickname=member.nickname,
        joined_at=member.joined_at,
    )


def _room_uuid(room_id: str) -> UUID:
    try:
        return UUID(room_id)
    except ValueError:
        raise RoomNotFound() from None


def _session_uuid(session_id: str) -> UUID:
    try:
        return UUID(session_id)
    except ValueError:
        raise NotAMember() from None


def utc_now() -> datetime:
    return datetime.now(UTC)


def join_room(db: DbSession, session_id: str, room_id: UUID) -> JoinRoomResponse:
    session_uuid = _session_uuid(session_id)
    with db.begin():
        # Lock before any membership read/write. Time is sampled after waiting,
        # so a queued join never makes a reservation decision with an old cutoff.
        repository.lock_room(db, room_id)
        room = repository.get_active_room(db, room_id, lock=True)
        if room is None:
            raise RoomNotFound()
        now = utc_now()
        since = now - timedelta(seconds=get_settings().nickname_hold_seconds)
        reserved = repository.reserved_members(db, room_id, since)
        own = next((member for member in reserved if member.session_id == session_uuid), None)
        nickname = (
            own.nickname if own else generate_nickname({member.nickname for member in reserved})
        )
        repository.upsert_member(db, room_id, session_uuid, nickname, now)
        response = JoinRoomResponse(room=JoinedRoom.model_validate(room), nickname=nickname)
    return response


def heartbeat_room(db: DbSession, session_id: str, room_id: UUID) -> None:
    with db.begin():
        if repository.get_active_room(db, room_id) is None:
            raise RoomNotFound()
        if not repository.heartbeat(db, room_id, _session_uuid(session_id), utc_now()):
            raise NotAMember()
