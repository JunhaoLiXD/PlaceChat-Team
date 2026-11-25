"""Message reporting routes (PlaceChat Technical Design §7.1)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import Admin, get_current_session, require_admin
from app.core.auth import Session as AuthSession
from app.core.db import get_db
from app.core.realtime import publish
from app.modules.safety import reports
from app.modules.safety.schemas import AdminReportResponse, ReportCreate, ReportResponse

router = APIRouter(tags=["reports"])
admin_router = APIRouter(
    prefix="/admin/reports", tags=["admin"], dependencies=[Depends(require_admin)]
)


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


@admin_router.get("", response_model=list[AdminReportResponse])
def list_pending_reports(
    db: Annotated[Session, Depends(get_db)],
    status: str = Query("pending", pattern="^pending$"),
) -> list[AdminReportResponse]:
    del status
    return [
        AdminReportResponse(
            **ReportResponse.model_validate(report).model_dump(),
            message=message,
            room=room,
        )
        for report, message, room in reports.get_pending_reports(db)
    ]


@admin_router.post("/{report_id}/remove-message", status_code=204)
def remove_reported_message(
    report_id: UUID,
    admin: Annotated[Admin, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    admin_id = UUID(admin.user_id)
    message = reports.remove_reported_message(db, report_id, admin_id)
    publish(f"room:{message.room_id}", "message.removed", {"id": str(message.id)})


@admin_router.post("/{report_id}/dismiss", status_code=204)
def dismiss_report(
    report_id: UUID,
    admin: Annotated[Admin, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    reports.dismiss_report(db, report_id, UUID(admin.user_id))
