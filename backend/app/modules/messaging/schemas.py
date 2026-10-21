"""Message request and response bodies (PlaceChat Technical Design §4, §7.1).

Owner: Junhao — PBI-14 (#18).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MessageCreate(BaseModel):
    """Length and blank checks run in the pipeline (step 3), not here, so the order holds."""

    model_config = ConfigDict(extra="forbid")

    body: str


class MessageResponse(BaseModel):
    """The broadcast payload and the POST response. Never includes `session_id` (§4)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    room_id: UUID
    nickname: str
    body: str
    created_at: datetime
