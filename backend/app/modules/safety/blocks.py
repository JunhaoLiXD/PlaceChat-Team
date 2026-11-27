"""Temporary block contract, pipeline step 2 (PlaceChat Technical Design §3.4).

Owner: Zhijie — PBI-42 (Sprint 2).
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.core.errors import Blocked, MessageNotFound, ReportNotFound
from app.modules.messaging.models import Message
from app.modules.safety.models import Block, Report


def utc_now() -> datetime:
    return datetime.now(UTC)


def _latest_expiry(db: DbSession, session_id: UUID) -> datetime | None:
    until = db.scalar(select(func.max(Block.expires_at)).where(Block.session_id == session_id))
    # SQLite omits timezone information; PostgreSQL returns an aware timestamptz.
    if until is not None and until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    return until


def block_reported_sender(
    db: DbSession, report_id: UUID, duration_minutes: int, admin_id: UUID
) -> Block:
    """Resolve the reported sender on the server and retain an audit record.

    Blocking does not remove the message or handle the report. A retained report
    can still identify a sender after removal or dismissal.
    """
    report = db.get(Report, report_id)
    if report is None:
        raise ReportNotFound()
    message = db.get(Message, report.message_id)
    if message is None:
        raise MessageNotFound()

    now = utc_now()
    until = now + timedelta(minutes=duration_minutes)
    previous_until = _latest_expiry(db, message.session_id)
    if previous_until is not None:
        until = max(until, previous_until)
    block = Block(
        id=uuid4(),
        session_id=message.session_id,
        reason=report.reason,
        created_by=admin_id,
        created_at=now,
        expires_at=until,
    )
    db.add(block)
    db.commit()
    return block


def check_not_blocked(db: DbSession, session_id: str) -> None:
    """Raise Blocked(until) across all rooms, strictly before the latest expiry."""
    until = _latest_expiry(db, UUID(session_id))
    if until is not None and until > utc_now():
        raise Blocked(until)
