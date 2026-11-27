"""Temporary sender blocks (PlaceChat Technical Design §7.1, E3)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Admin, require_admin
from app.core.db import get_db
from app.modules.safety import blocks
from app.modules.safety.schemas import BlockCreate, BlockResponse

router = APIRouter(prefix="/admin/blocks", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("", response_model=BlockResponse)
def block_reported_sender(
    data: BlockCreate,
    admin: Annotated[Admin, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> BlockResponse:
    block = blocks.block_reported_sender(
        db, data.report_id, data.duration_minutes, UUID(admin.user_id)
    )
    return BlockResponse.model_validate(block)
