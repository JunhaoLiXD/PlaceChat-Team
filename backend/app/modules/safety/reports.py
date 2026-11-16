"""Message reporting service (PlaceChat Technical Design §5.1, §7.1)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.errors import AlreadyReported, CannotReportOwn, MessageNotFound
from app.modules.messaging.models import Message
from app.modules.safety.models import Report


def report_message(
    db: DbSession, reporter_session_id: str, message_id: UUID, reason: str | None
) -> Report:
    """Store one anonymous report without exposing the reporter in the API response."""
    message = db.get(Message, message_id)
    if message is None or message.removed_at is not None:
        raise MessageNotFound()
    if str(message.session_id) == reporter_session_id:
        raise CannotReportOwn()

    reporter_id = UUID(reporter_session_id)
    existing = (
        db.query(Report).filter_by(message_id=message_id, reporter_session_id=reporter_id).first()
    )
    if existing is not None:
        raise AlreadyReported()

    report = Report(
        id=uuid4(),
        message_id=message.id,
        room_id=message.room_id,
        reporter_session_id=reporter_id,
        reason=reason,
        status="pending",
        created_at=datetime.now(UTC),
    )
    try:
        with db.begin_nested():
            db.add(report)
            db.flush()
    except IntegrityError:
        if (
            db.query(Report)
            .filter_by(message_id=message_id, reporter_session_id=reporter_id)
            .first()
            is not None
        ):
            raise AlreadyReported() from None
        raise
    db.commit()
    return report
