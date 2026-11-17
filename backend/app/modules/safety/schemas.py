"""Message reporting request and response bodies."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.modules.messaging.schemas import MessageResponse
from app.modules.rooms.schemas import JoinedRoom

ReportReason = Literal["harassment", "spam", "other"]
ReportStatus = Literal["pending", "removed", "dismissed"]


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: ReportReason | None = None


class ReportResponse(BaseModel):
    """A report representation that never includes reporter_session_id."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    message_id: UUID
    room_id: UUID
    reason: ReportReason | None
    status: ReportStatus
    created_at: datetime


class AdminReportResponse(ReportResponse):
    """A pending report with the content and room an administrator must review."""

    message: MessageResponse
    room: JoinedRoom
