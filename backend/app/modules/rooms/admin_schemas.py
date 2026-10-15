"""Admin room request and response bodies (PlaceChat Technical Design §7.1, E1).

Owner: Junhao — PBI-22 (#26).
"""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.modules.rooms.schemas import RoomCategory

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class RoomCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonBlankText
    description: NonBlankText
    category: RoomCategory
    latitude: Latitude
    longitude: Longitude


class RoomUpdate(BaseModel):
    """Partial edit: only the fields sent are changed. Status changes go through archive."""

    model_config = ConfigDict(extra="forbid")

    name: NonBlankText | None = None
    description: NonBlankText | None = None
    category: RoomCategory | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None

    @model_validator(mode="after")
    def check_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Send at least one field to change.")
        for field in sorted(self.model_fields_set):
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null.")
        return self


class AdminRoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    category: RoomCategory
    latitude: float
    longitude: float
    status: Literal["active", "archived"]
    created_at: datetime
    updated_at: datetime
