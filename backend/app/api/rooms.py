from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.rooms.schemas import RoomResponse
from app.modules.rooms.service import list_rooms

router = APIRouter(tags=["rooms"])


@router.get("/rooms", response_model=list[RoomResponse])
def get_rooms(db: Annotated[Session, Depends(get_db)]) -> list[RoomResponse]:
    return list_rooms(db)
