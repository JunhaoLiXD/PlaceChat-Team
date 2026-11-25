"""Admin blocked-word routes (PlaceChat Technical Design §7.1, D3). Owner: Junhao — PBI-37 (#72)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.core.db import get_db
from app.modules.safety import blocked_words
from app.modules.safety.schemas import BlockedWordCreate, BlockedWordResponse

# The admin check sits on the router, so no route here can forget it.
router = APIRouter(
    prefix="/admin/blocked-words", tags=["admin"], dependencies=[Depends(require_admin)]
)

Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[BlockedWordResponse])
def list_blocked_words(db: Db) -> list[BlockedWordResponse]:
    return [BlockedWordResponse.model_validate(word) for word in blocked_words.list_words(db)]


@router.post("", response_model=BlockedWordResponse, status_code=201)
def add_blocked_word(body: BlockedWordCreate, db: Db) -> BlockedWordResponse:
    return BlockedWordResponse.model_validate(blocked_words.add_word(db, body.word))


@router.delete("/{word_id}", status_code=204)
def delete_blocked_word(word_id: UUID, db: Db) -> Response:
    blocked_words.delete_word(db, word_id)
    return Response(status_code=204)
