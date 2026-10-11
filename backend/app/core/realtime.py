"""Realtime publisher (PlaceChat Technical Design §6.5). Owner: Yufei — PBI-15 (#19)."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def publish(topic: str, event: str, payload: dict[str, Any]) -> None:
    """Broadcast `event` with `payload` to the private Realtime channel `topic`.

    Never put `session_id` in a payload. Failures are logged, not raised.
    Stub until PBI-15 (#19): logs the event and sends nothing.
    """
    logger.info("realtime stub: %s %s", topic, event)
