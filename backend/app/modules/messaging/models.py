"""Message mapping. SQL migrations remain the source of truth for the schema."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    room_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("rooms.id"))
    session_id: Mapped[UUID] = mapped_column(Uuid)
    nickname: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[UUID | None] = mapped_column(Uuid)
