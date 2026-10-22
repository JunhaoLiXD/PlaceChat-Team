"""Message pipeline (PlaceChat Technical Design §4).

`validate_message` is step 3 (Yufei — PBI-12, #16). `send_message` runs all seven steps
(Junhao — PBI-14, #18). Steps 1, 2, 4, and 5 belong to other modules and are called through
their contracts (§3.4); some are still stubs.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.realtime import publish
from app.modules.messaging import repository
from app.modules.messaging.models import Message
from app.modules.messaging.schemas import MessageResponse
from app.modules.rooms.service import ensure_member
from app.modules.safety.blocks import check_not_blocked
from app.modules.safety.rate_limit import check_rate_limit
from app.modules.safety.word_filter import filter_text


def validate_message(text: str) -> str:
    """Trim and validate message content for the message pipeline."""
    trimmed = text.strip()
    max_length = get_settings().message_max_length

    if not trimmed:
        raise ValidationFailed("Message cannot be empty.")
    if len(trimmed) > max_length:
        raise ValidationFailed(f"Message must be {max_length} characters or fewer.")

    return trimmed


def send_message(db: DbSession, session_id: str, room_id: UUID, text: str) -> MessageResponse:
    """Run the seven steps in order. The first failing step raises, so a rejected message is
    never stored or broadcast."""
    membership = ensure_member(db, session_id, str(room_id))  # 1. joined an active room
    check_not_blocked(db, session_id)  # 2. not blocked
    body = validate_message(text)  # 3. trimmed, not empty, not too long
    check_rate_limit(db, session_id)  # 4. under the sending limit
    body = filter_text(body)  # 5. blocked words masked

    message = Message(  # 6. store
        id=uuid4(),
        room_id=room_id,
        session_id=UUID(session_id),
        nickname=membership.nickname,
        body=body,
        created_at=datetime.now(UTC),
    )
    repository.add_message(db, message)
    db.commit()

    # 7. publish after the commit; publish() logs failures and the message stays in history.
    response = MessageResponse.model_validate(message)
    publish(f"room:{room_id}", "message.created", response.model_dump(mode="json"))
    return response
