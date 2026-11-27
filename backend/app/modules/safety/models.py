"""Safety-related database mappings."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

ReportStatus = Literal["pending", "removed", "dismissed"]


class BlockedWord(Base):
    __tablename__ = "blocked_words"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    word: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[UUID] = mapped_column(Uuid)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("message_id", "reporter_session_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    message_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("messages.id"))
    room_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("rooms.id"))
    reporter_session_id: Mapped[UUID] = mapped_column(Uuid)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handled_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
