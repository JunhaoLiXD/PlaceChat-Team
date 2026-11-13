"""One lifespan-owned presence sweeper for the single backend instance (§5.2)."""

import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.db import create_session
from app.modules.rooms import repository, service

logger = logging.getLogger(__name__)


def sweep_presence() -> None:
    # Release the discovery transaction before processing or publishing for any room.
    with create_session() as db:
        room_ids = repository.active_room_ids(db)
    for room_id in room_ids:
        try:
            with create_session() as db:
                service.sweep_room_presence(db, room_id)
        except Exception:
            logger.exception("Presence sweep failed for room %s", room_id)


async def run_presence_sweeper(stop: asyncio.Event) -> None:
    interval = get_settings().sweeper_interval_seconds
    while not stop.is_set():
        try:
            # Only the synchronous DB iteration uses a request-pool thread.
            # Count notification never waits for the background network publisher.
            await run_in_threadpool(sweep_presence)
        except Exception:
            logger.exception("Presence sweep iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
