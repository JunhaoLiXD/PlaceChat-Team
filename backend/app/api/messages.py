"""Message routes (PlaceChat Technical Design §4, §7.1). Owner: Junhao — PBI-14 (#18)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Session as AuthSession
from app.core.auth import get_current_session
from app.core.db import get_db
from app.modules.messaging import service
from app.modules.messaging.schemas import MessageCreate, MessageResponse

router = APIRouter(tags=["messages"])


@router.post("/rooms/{room_id}/messages", response_model=MessageResponse, status_code=201)
def send_message(
    room_id: UUID,
    data: MessageCreate,
    session: Annotated[AuthSession, Depends(get_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponse:
    return service.send_message(db, session.id, room_id, data.body)
