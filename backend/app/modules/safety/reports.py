"""Message reporting service (PlaceChat Technical Design §5.1, §7.1)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.errors import AlreadyReported, CannotReportOwn, MessageNotFound, ReportNotFound
from app.modules.messaging.models import Message
from app.modules.rooms.models import Room
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


def get_pending_reports(db: DbSession) -> list[tuple[Report, Message, Room]]:
    statement = (
        select(Report, Message, Room)
        .join(Message, Message.id == Report.message_id)
        .join(Room, Room.id == Report.room_id)
        .where(Report.status == "pending")
        .order_by(Report.created_at, Report.id)
    )
    return list(db.execute(statement).all())


def remove_reported_message(db: DbSession, report_id: UUID, admin_id: UUID) -> Message:
    report = db.get(Report, report_id)
    if report is None or report.status != "pending":
        raise ReportNotFound()

    message = db.get(Message, report.message_id)
    if message is None:
        raise MessageNotFound()

    now = datetime.now(UTC)
    message.removed_at = now
    message.removed_by = admin_id
    pending_reports = db.scalars(
        select(Report).where(Report.message_id == message.id, Report.status == "pending")
    )
    for pending_report in pending_reports:
        pending_report.status = "removed"
        pending_report.handled_at = now
        pending_report.handled_by = admin_id
    db.commit()
    return message


def dismiss_report(db: DbSession, report_id: UUID, admin_id: UUID) -> Report:
    report = db.get(Report, report_id)
    if report is None or report.status != "pending":
        raise ReportNotFound()

    report.status = "dismissed"
    report.handled_at = datetime.now(UTC)
    report.handled_by = admin_id
    db.commit()
    return report
