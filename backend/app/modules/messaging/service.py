"""Message pipeline validation and storage services."""

from app.core.config import get_settings
from app.core.errors import ValidationFailed


def validate_message(text: str) -> str:
    """Trim and validate message content for the message pipeline."""
    trimmed = text.strip()
    max_length = get_settings().message_max_length

    if not trimmed:
        raise ValidationFailed("Message cannot be empty.")
    if len(trimmed) > max_length:
        raise ValidationFailed(f"Message must be {max_length} characters or fewer.")

    return trimmed
