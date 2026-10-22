from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Session as Identity
from app.core.auth import get_current_session
from app.core.db import get_db
from app.modules.rooms import service
from app.modules.rooms.schemas import HeartbeatResponse, JoinRoomResponse, RoomResponse
from app.modules.rooms.service import list_rooms

router = APIRouter(tags=["rooms"])


@router.get("/rooms", response_model=list[RoomResponse])
def get_rooms(db: Annotated[Session, Depends(get_db)]) -> list[RoomResponse]:
    return list_rooms(db)


@router.post("/rooms/{room_id}/join", response_model=JoinRoomResponse)
def join_room(
    room_id: UUID,
    current: Annotated[Identity, Depends(get_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> JoinRoomResponse:
    return service.join_room(db, current.id, room_id)


@router.post("/rooms/{room_id}/heartbeat", response_model=HeartbeatResponse)
def heartbeat_room(
    room_id: UUID,
    current: Annotated[Identity, Depends(get_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> HeartbeatResponse:
    service.heartbeat_room(db, current.id, room_id)
    return HeartbeatResponse()
