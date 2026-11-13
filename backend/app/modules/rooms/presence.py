"""One lifespan-owned, coalescing publisher for the two count events (§7.3)."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Lock
from uuid import UUID

import httpx

from app.core.realtime import create_async_client
from app.core.realtime import publish_async as publish

logger = logging.getLogger(__name__)
SHUTDOWN_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class PendingCount:
    """A local ticket reserved under the room lock; notification follows commit."""

    publisher: "CountPublisher"
    room_id: UUID
    revision: int
    count: int

    def notify_committed(self) -> None:
        self.publisher.notify(self)


class CountPublisher:
    """One task, one pending value per room, and at most one scheduled wakeup.

    Room metadata is O(rooms), never O(requests). Revisions survive delivery so a
    delayed older notification cannot resurrect an already superseded count.
    """

    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()
        self._lock = Lock()
        self._revision = 0
        self._latest: dict[UUID, int] = {}
        self._pending: dict[UUID, PendingCount] = {}
        self._delivered: dict[tuple[UUID, str], int] = {}
        self._wake = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()
        self._scheduled = False
        self._active = False
        self._closed = False
        self.task = asyncio.create_task(self._run(), name="presence-publisher")

    def reserve(self, room_id: UUID, count: int) -> PendingCount:
        # Called while the room's advisory lock still establishes commit order.
        with self._lock:
            self._revision += 1
            return PendingCount(self, room_id, self._revision, count)

    def notify(self, update: PendingCount) -> None:
        with self._lock:
            if self._closed or update.revision <= self._latest.get(update.room_id, 0):
                return
            self._latest[update.room_id] = update.revision
            self._pending[update.room_id] = update
            self._schedule()

    def _schedule(self) -> None:
        if not self._scheduled:
            self._scheduled = True
            self.loop.call_soon_threadsafe(self._wake.set)

    async def wait_idle(self) -> None:
        """Wait for a delivery checkpoint, used by tests and graceful shutdown."""
        while True:
            with self._lock:
                if not self._pending and not self._active:
                    return
                self._idle.clear()
            await self._idle.wait()

    async def _send(self, client: httpx.AsyncClient, update: PendingCount) -> None:
        room_id, count = update.room_id, update.count
        for topic, event, payload in (
            (f"room:{room_id}", "presence.updated", {"count": count}),
            ("rooms", "room.count", {"room_id": str(room_id), "count": count}),
        ):
            key = (room_id, event)
            if self._delivered.get(key) == count:
                continue
            try:
                if await publish(client, topic, event, payload):
                    self._delivered[key] = count
                else:
                    # Subscribers may have received it even if acknowledgement failed.
                    self._delivered.pop(key, None)
            except Exception:
                self._delivered.pop(key, None)
                # A failure on one channel must not skip the other, or kill the worker.
                logger.exception("Participant count publish failed for %s %s", topic, event)

    async def _run(self) -> None:
        try:
            async with create_async_client() as client:
                while True:
                    await self._wake.wait()
                    with self._lock:
                        if not self._pending:
                            self._scheduled = False
                            self._wake.clear()
                            self._idle.set()
                            if self._closed:
                                return
                            continue
                        room_id = next(iter(self._pending))
                        update = self._pending.pop(room_id)
                        self._active = True
                    try:
                        await self._send(client, update)
                    except Exception:
                        logger.exception("Participant count worker recovered from delivery failure")
                    finally:
                        with self._lock:
                            self._active = False
                            if not self._pending:
                                self._idle.set()
                    # Also yield when transport is unconfigured or a value was deduplicated.
                    await asyncio.sleep(0)
        finally:
            with self._lock:
                self._active = False
                self._pending.clear()
                self._latest.clear()
                self._delivered.clear()
                self._idle.set()

    async def close(self, timeout: float = SHUTDOWN_TIMEOUT_SECONDS) -> None:
        with self._lock:
            self._closed = True
            self._schedule()
        if self.task.cancelled():
            return
        try:
            await asyncio.wait_for(self.task, timeout)
        except TimeoutError:
            # wait_for cancels the async HTTP operation and closes its owned client.
            logger.warning("Presence publisher shutdown deadline reached; pending counts dropped")


_owner_lock = Lock()
_publisher: CountPublisher | None = None


@asynccontextmanager
async def publisher_lifespan() -> AsyncIterator[CountPublisher]:
    global _publisher
    with _owner_lock:
        if _publisher is not None:
            raise RuntimeError("A presence publisher already owns this process")
        publisher = CountPublisher()
        _publisher = publisher
    try:
        yield publisher
    finally:
        try:
            await publisher.close()
        finally:
            # Keep ownership until the old worker/client has actually closed.
            with _owner_lock:
                _publisher = None


def reserve_count(room_id: UUID, count: int | None) -> PendingCount | None:
    if count is None:
        return None
    with _owner_lock:
        publisher = _publisher
    return publisher.reserve(room_id, count) if publisher is not None else None
