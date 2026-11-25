from datetime import datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.rooms.models import Room, RoomMember, RoomPresenceCount


def active_room_ids(db: Session) -> list[UUID]:
    return list(db.scalars(select(Room.id).where(Room.status == "active").order_by(Room.id)))


def participant_count(db: Session, room_id: UUID, since: datetime) -> int:
    query = (
        select(func.count())
        .select_from(RoomMember)
        .where(
            RoomMember.room_id == room_id,
            RoomMember.left_at.is_(None),
            RoomMember.last_seen_at >= since,
        )
    )
    return db.scalar(query)


def get_presence_snapshot(
    db: Session, room_id: UUID, *, since: datetime | None = None
) -> RoomPresenceCount:
    """Initialize under the room lock, before a membership change.

    The first sweep includes all joined members in its baseline so preexisting stale
    memberships also get a timeout update, including zero. Subsequent observations use
    the persisted snapshot. No membership timestamps or nickname holds are changed.
    """
    state = db.get(RoomPresenceCount, room_id)
    if state is None:
        initial_count = (
            participant_count(db, room_id, since)
            if since is not None
            else db.scalar(
                select(func.count())
                .select_from(RoomMember)
                .where(RoomMember.room_id == room_id, RoomMember.left_at.is_(None))
            )
        )
        state = RoomPresenceCount(room_id=room_id, participant_count=initial_count)
        db.add(state)
        db.flush()
    return state


def refresh_presence_count(db: Session, state: RoomPresenceCount, since: datetime) -> int | None:
    """Record one observation in the caller's locked transaction; return only changes."""
    count = participant_count(db, state.room_id, since)
    if count == state.participant_count:
        return None
    state.participant_count = count
    db.flush()
    return count


def list_active_rooms(db: Session, since: datetime) -> list[tuple[Room, int]]:
    present = (
        select(RoomMember.room_id, func.count().label("participant_count"))
        .where(RoomMember.left_at.is_(None), RoomMember.last_seen_at >= since)
        .group_by(RoomMember.room_id)
        .subquery()
    )
    query = (
        select(Room, func.coalesce(present.c.participant_count, 0))
        .outerjoin(present, present.c.room_id == Room.id)
        .where(Room.status == "active")
        .order_by(Room.name)
    )
    return [(room, count) for room, count in db.execute(query)]


def room_lock_key(room_id: UUID) -> int:
    """Stable signed bigint, shared by all processes; never use Python's randomized hash."""
    digest = sha256(f"placechat:room:{room_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def lock_room(db: Session, room_id: UUID) -> None:
    db.execute(select(func.pg_advisory_xact_lock(room_lock_key(room_id))))


def get_active_room(db: Session, room_id: UUID, *, lock: bool = False) -> Room | None:
    query = select(Room).where(Room.id == room_id, Room.status == "active")
    if lock:
        # Keep an administrator from archiving this room during join or leave.
        query = query.with_for_update(read=True)
    return db.scalar(query)


def reserved_members(db: Session, room_id: UUID, since: datetime) -> list[RoomMember]:
    return list(
        db.scalars(
            select(RoomMember).where(
                RoomMember.room_id == room_id,
                RoomMember.left_at.is_(None),
                RoomMember.last_seen_at >= since,
            )
        )
    )


def get_member(db: Session, room_id: UUID, session_id: UUID) -> RoomMember | None:
    return db.get(RoomMember, (room_id, session_id))


def upsert_member(
    db: Session, room_id: UUID, session_id: UUID, nickname: str, now: datetime
) -> RoomMember:
    """Insert/update under the room's transaction lock, including repeat joins."""
    member = get_member(db, room_id, session_id)
    if member is None:
        member = RoomMember(room_id=room_id, session_id=session_id)
        db.add(member)
    member.nickname = nickname
    member.joined_at = now
    member.last_seen_at = now
    member.left_at = None
    db.flush()
    return member


def heartbeat(db: Session, room_id: UUID, session_id: UUID, now: datetime) -> bool:
    # The predicate is checked by the UPDATE itself: a concurrent Leave cannot be undone.
    result = db.execute(
        update(RoomMember)
        .where(
            RoomMember.room_id == room_id,
            RoomMember.session_id == session_id,
            RoomMember.left_at.is_(None),
        )
        .values(last_seen_at=now)
        .returning(RoomMember.session_id)
    )
    return result.scalar_one_or_none() is not None


def leave(db: Session, room_id: UUID, session_id: UUID, now: datetime) -> bool:
    """Mark only this joined membership left, under the room's transaction lock."""
    result = db.execute(
        update(RoomMember)
        .where(
            RoomMember.room_id == room_id,
            RoomMember.session_id == session_id,
            RoomMember.left_at.is_(None),
        )
        .values(left_at=now)
        .returning(RoomMember.session_id)
    )
    return result.scalar_one_or_none() is not None
