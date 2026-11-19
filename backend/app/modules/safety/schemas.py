"""Message reporting request and response bodies."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.core.config import get_settings
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


BlockedWordText = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1)
]


class BlockedWordCreate(BaseModel):
    """A word or phrase to mask in new messages (D3). Stored trimmed and lowercase."""

    model_config = ConfigDict(extra="forbid")

    word: BlockedWordText

    @field_validator("word")
    @classmethod
    def fits_in_a_message(cls, word: str) -> str:
        # A blocked word longer than a message could never match one.
        if len(word) > get_settings().message_max_length:
            raise ValueError(f"must be at most {get_settings().message_max_length} characters")
        return word


class BlockedWordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    word: str
    created_at: datetime
