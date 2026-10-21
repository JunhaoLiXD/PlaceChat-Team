"""Room mapping. SQL migrations remain the source of truth for the schema."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RoomMember(Base):
    __tablename__ = "room_members"

    room_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("rooms.id"), primary_key=True)
    # The migration owns the cascading auth.users FK; Supabase owns that external table.
    session_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    nickname: Mapped[str] = mapped_column(Text)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
