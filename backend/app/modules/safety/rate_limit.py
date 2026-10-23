"""Rate limit contract, pipeline step 4 (PlaceChat Technical Design §5.2).

Owner: Yufei — PBI-19 (#23).
"""

from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.errors import RateLimited
from app.modules.messaging.models import Message


def utc_now() -> datetime:
    return datetime.now(UTC)


def check_rate_limit(db: DbSession, session_id: str) -> None:
    """Raise RateLimited when the session has reached its cross-room message limit."""
    settings = get_settings()
    now = utc_now()
    cutoff = now - timedelta(seconds=settings.rate_limit_window_seconds)
    recent_messages = list(
        db.scalars(
            select(Message.created_at)
            .where(Message.session_id == UUID(session_id), Message.created_at >= cutoff)
            .order_by(Message.created_at)
            .limit(settings.rate_limit_max_messages)
        )
    )

    if len(recent_messages) < settings.rate_limit_max_messages:
        return

    oldest = recent_messages[0]
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=UTC)
    retry_after = max(
        1,
        ceil(
            (
                oldest + timedelta(seconds=settings.rate_limit_window_seconds) - now
            ).total_seconds()
        ),
    )
    raise RateLimited(retry_after)
