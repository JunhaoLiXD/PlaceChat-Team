"""Admin room routes (PlaceChat Technical Design §7.1, E1). Owner: Junhao — PBI-22 (#26)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.core.db import get_db
from app.modules.rooms import admin_service
from app.modules.rooms.admin_schemas import AdminRoomResponse, RoomCreate, RoomUpdate

# The admin check sits on the router, so no route here can forget it.
router = APIRouter(prefix="/admin/rooms", tags=["admin"], dependencies=[Depends(require_admin)])

Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[AdminRoomResponse])
def list_rooms(db: Db) -> list[AdminRoomResponse]:
    return admin_service.list_rooms(db)


@router.post("", response_model=AdminRoomResponse, status_code=201)
def create_room(body: RoomCreate, db: Db) -> AdminRoomResponse:
    return admin_service.create_room(db, body)


@router.patch("/{room_id}", response_model=AdminRoomResponse)
def update_room(room_id: UUID, body: RoomUpdate, db: Db) -> AdminRoomResponse:
    return admin_service.update_room(db, room_id, body)


@router.post("/{room_id}/archive", response_model=AdminRoomResponse)
def archive_room(room_id: UUID, db: Db) -> AdminRoomResponse:
    return admin_service.archive_room(db, room_id)
