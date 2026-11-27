"""Safety request and response bodies."""

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


class BlockCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: UUID
    duration_minutes: Literal[15, 60, 1440]

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def allowed_duration(cls, value: object) -> object:
        options = get_settings().block_duration_options_minutes
        if type(value) is not int or value not in options:
            raise ValueError(f"must be one of {options} minutes")
        return value


class BlockResponse(BaseModel):
    """Confirmation without exposing a sender's cross-room identity."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    expires_at: datetime


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
