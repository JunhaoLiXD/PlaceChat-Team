"""Message reporting routes (PlaceChat Technical Design §7.1)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import Session as AuthSession
from app.core.auth import get_current_session
from app.core.db import get_db
from app.modules.safety import reports
from app.modules.safety.schemas import ReportCreate, ReportResponse

router = APIRouter(tags=["reports"])


@router.post(
    "/messages/{message_id}/reports",
    response_model=ReportResponse,
    status_code=201,
)
def create_message_report(
    message_id: UUID,
    data: ReportCreate,
    session: Annotated[AuthSession, Depends(get_current_session)],
    db: Annotated[Session, Depends(get_db)],
) -> ReportResponse:
    report = reports.report_message(db, session.id, message_id, data.reason)
    return ReportResponse.model_validate(report)
