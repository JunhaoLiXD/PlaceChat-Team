from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RoomCategory = Literal["library", "dining", "student life", "academic", "recreation"]


class RoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    category: RoomCategory
    latitude: float
    longitude: float
    participant_count: int = Field(default=0, ge=0)


class JoinedRoom(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str


class JoinRoomResponse(BaseModel):
    room: JoinedRoom
    nickname: str


class HeartbeatResponse(BaseModel):
    status: Literal["ok"] = "ok"


class LeaveResponse(BaseModel):
    status: Literal["ok"] = "ok"
