"""The two public count events in Technical Design §7.3; no participant identifiers."""

import logging
from collections import deque
from dataclasses import dataclass, field
from threading import Event, Lock
from uuid import UUID

from app.core.realtime import publish

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class PendingCount:
    """One count reserved under the DB lock, then published after commit.

    The single backend process preserves commit order per room even when a publisher
    is slow. Waiting publishers hold no database locks; other rooms are independent.
    """

    room_id: UUID
    count: int
    _ready: Event = field(default_factory=Event, repr=False)

    def publish(self) -> None:
        try:
            self._ready.wait()
            publish_count(self.room_id, self.count)
        finally:
            self.cancel()

    def cancel(self) -> None:
        """Release the next publisher on completion or transaction rollback."""
        with _pending_lock:
            queue = _pending[self.room_id]
            queue.remove(self)
            if queue:
                queue[0]._ready.set()
            else:
                del _pending[self.room_id]


_pending_lock = Lock()
_pending: dict[UUID, deque[PendingCount]] = {}


def reserve_count(room_id: UUID, count: int | None) -> PendingCount | None:
    if count is None:
        return None
    pending = PendingCount(room_id, count)
    with _pending_lock:
        queue = _pending.setdefault(room_id, deque())
        queue.append(pending)
        if len(queue) == 1:
            pending._ready.set()
    return pending


def publish_count(room_id: UUID, count: int | None) -> None:
    if count is None:
        return
    for topic, event, payload in (
        (f"room:{room_id}", "presence.updated", {"count": count}),
        ("rooms", "room.count", {"room_id": str(room_id), "count": count}),
    ):
        try:
            publish(topic, event, payload)
        except Exception:
            # The transport already logs HTTP failures. Guard unexpected failures too,
            # and still try the other channel after a successful database commit.
            logger.exception("Participant count publish failed for %s %s", topic, event)
