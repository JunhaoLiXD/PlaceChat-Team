"""Room membership contract (PlaceChat Technical Design §3.4, §5.2).

Owner: Zhijie — PBI-07 (#11).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.errors import NotAMember, RoomNotFound
from app.modules.nicknames.service import generate_nickname
from app.modules.rooms import presence, repository
from app.modules.rooms.models import Room
from app.modules.rooms.schemas import JoinedRoom, JoinRoomResponse, RoomResponse


def list_rooms(db: DbSession) -> list[RoomResponse]:
    """List active rooms with counts at one inclusive presence cutoff."""
    since = presence_since(utc_now())
    return [
        RoomResponse.model_validate(room).model_copy(update={"participant_count": count})
        for room, count in repository.list_active_rooms(db, since)
    ]


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
    # revokes a joined membership. Only explicit Leave ends it.
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


def presence_since(now: datetime) -> datetime:
    return now - timedelta(seconds=get_settings().presence_timeout_seconds)


@contextmanager
def _presence_transaction(
    db: DbSession, room_id: UUID, *, sweep: bool = False
) -> Iterator[tuple[Room, datetime]]:
    pending = None
    with db.begin():
        # Sample time only after waiting for the room's transaction lock.
        repository.lock_room(db, room_id)
        room = repository.get_active_room(db, room_id, lock=True)
        if room is None:
            raise RoomNotFound()
        now = utc_now()
        since = presence_since(now)
        state = repository.get_presence_snapshot(db, room_id, since=None if sweep else since)
        yield room, now
        count = repository.refresh_presence_count(db, state, since)
        # Reserve a revision under the DB lock, without registering any queued work.
        pending = presence.reserve_count(room_id, count)
    # Commit failure/rollback never reaches this quick, nonblocking notification.
    if pending is not None:
        pending.notify_committed()


def join_room(db: DbSession, session_id: str, room_id: UUID) -> JoinRoomResponse:
    session_uuid = _session_uuid(session_id)
    with _presence_transaction(db, room_id) as (room, now):
        since = now - timedelta(seconds=get_settings().nickname_hold_seconds)
        reserved = repository.reserved_members(db, room_id, since)
        own = next((member for member in reserved if member.session_id == session_uuid), None)
        if own:
            nickname = own.nickname
        else:
            taken = {member.nickname for member in reserved}
            previous = repository.get_member(db, room_id, session_uuid)
            if previous is not None and previous.left_at is not None:
                # A fresh name for this caller; the old name is still free for others.
                taken.add(previous.nickname)
            nickname = generate_nickname(taken)
        repository.upsert_member(db, room_id, session_uuid, nickname, now)
        response = JoinRoomResponse(room=JoinedRoom.model_validate(room), nickname=nickname)
    return response


def heartbeat_room(db: DbSession, session_id: str, room_id: UUID) -> None:
    with _presence_transaction(db, room_id) as (_, now):
        if not repository.heartbeat(db, room_id, _session_uuid(session_id), now):
            raise NotAMember()


def leave_room(db: DbSession, session_id: str, room_id: UUID) -> None:
    with _presence_transaction(db, room_id) as (_, now):
        if not repository.leave(db, room_id, _session_uuid(session_id), now):
            raise NotAMember()


def sweep_room_presence(db: DbSession, room_id: UUID) -> None:
    """Reconcile one room, including pending timeouts, without ending membership."""
    try:
        with _presence_transaction(db, room_id, sweep=True):
            pass
    except RoomNotFound:
        # Discovery and the locked transaction use separate sessions; an archive
        # between them makes this room a no-op.
        return
