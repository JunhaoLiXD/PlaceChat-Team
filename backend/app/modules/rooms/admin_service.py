"""Create, edit, and archive rooms (PlaceChat Technical Design §2.2 E1, §7.1, §7.3).

Owner: Junhao — PBI-22 (#26).

Every change commits first and broadcasts afterwards, so clients that refetch on `room.changed`
already see the new data.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.errors import RoomNotFound, ValidationFailed
from app.core.realtime import publish
from app.modules.rooms import admin_repository as repository
from app.modules.rooms.admin_schemas import AdminRoomResponse, RoomCreate, RoomUpdate
from app.modules.rooms.models import Room

ROOMS_TOPIC = "rooms"


def create_room(db: DbSession, data: RoomCreate) -> AdminRoomResponse:
    _ensure_name_available(db, data.name)
    now = datetime.now(UTC)
    room = Room(id=uuid4(), status="active", created_at=now, updated_at=now, **data.model_dump())
    repository.add_room(db, room)
    _commit(db, data.name)
    return _changed(db, room)


def update_room(db: DbSession, room_id: UUID, data: RoomUpdate) -> AdminRoomResponse:
    room = _get_active_room(db, room_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        _ensure_name_available(db, changes["name"], exclude_id=room.id)
    for field, value in changes.items():
        setattr(room, field, value)
    # The database trigger also sets updated_at; setting it here keeps other databases honest.
    room.updated_at = datetime.now(UTC)
    _commit(db, changes.get("name", room.name))
    return _changed(db, room)


def archive_room(db: DbSession, room_id: UUID) -> AdminRoomResponse:
    """Hide the room from the list and close it for people inside. History is kept."""
    room = _get_active_room(db, room_id)
    room.status = "archived"
    room.updated_at = datetime.now(UTC)
    db.commit()
    response = _changed(db, room)
    publish(f"room:{room.id}", "room.archived", {"room_id": str(room.id)})
    return response


def _get_active_room(db: DbSession, room_id: UUID) -> Room:
    room = repository.get_room(db, room_id)
    if room is None or room.status != "active":
        raise RoomNotFound()
    return room


def _ensure_name_available(db: DbSession, name: str, exclude_id: UUID | None = None) -> None:
    if repository.name_taken(db, name, exclude_id):
        raise ValidationFailed(f'A room named "{name}" already exists.')


def _commit(db: DbSession, name: str) -> None:
    """Commit, turning a lost race on the unique name into the same error as the pre-check."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if repository.name_taken(db, name):
            raise ValidationFailed(f'A room named "{name}" already exists.') from None
        raise


def _changed(db: DbSession, room: Room) -> AdminRoomResponse:
    db.refresh(room)
    publish(ROOMS_TOPIC, "room.changed", {"room_id": str(room.id)})
    return AdminRoomResponse.model_validate(room)
