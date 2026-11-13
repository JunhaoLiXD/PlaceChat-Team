"""Deterministic mailbox, ordering, failure, and lifespan checks; no live transport."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest

from app.core import realtime
from app.core.config import Settings
from app.main import create_app
from app.modules.rooms import presence


def events(room, *counts):
    return [
        item
        for count in counts
        for item in (
            (f"room:{room}", "presence.updated", {"count": count}),
            ("rooms", "room.count", {"room_id": str(room), "count": count}),
        )
    ]


def test_blocked_delivery_coalesces_to_final_zero_with_one_worker(monkeypatch):
    async def scenario():
        room = uuid4()
        entered, release = asyncio.Event(), asyncio.Event()
        sent = []

        async def publish(client, topic, event, payload):
            if not entered.is_set():
                entered.set()
                await release.wait()
            sent.append((topic, event, payload))
            return True

        monkeypatch.setattr(presence, "publish", publish)
        async with presence.publisher_lifespan() as worker:
            worker.reserve(room, 1).notify_committed()
            await asyncio.wait_for(entered.wait(), 1)
            for count in range(2, 1002):
                worker.reserve(room, count).notify_committed()
            worker.reserve(room, 0).notify_committed()
            assert len(worker._pending) == 1
            assert (
                len([t for t in asyncio.all_tasks() if t.get_name() == "presence-publisher"]) == 1
            )
            release.set()
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert sent == events(room, 1, 0)
        assert worker.task.done()
        assert not worker._pending

    asyncio.run(scenario())


@pytest.mark.parametrize("failed_event", ["presence.updated", "room.count"])
@pytest.mark.parametrize("failure", ["false", "exception"])
@pytest.mark.parametrize("correction", [1, 2])
def test_uncertain_delivery_invalidates_only_affected_channel(
    monkeypatch, failed_event, failure, correction
):
    async def scenario():
        room, other_room = uuid4(), uuid4()
        received = []
        failed = False
        settings = Settings(
            _env_file=None,
            supabase_url="https://test.supabase.co",
            supabase_secret_key="sb_secret_test",
        )

        def deliver(request):
            nonlocal failed
            topic, event = request.url.path.split("/broadcast/", 1)[1].split("/events/")
            payload = json.loads(request.content)
            received.append((topic, event, payload))
            # Subscribers receive the count before its acknowledgement is lost.
            if event == failed_event and payload["count"] == 2 and not failed:
                failed = True
                raise httpx.ReadTimeout("response lost after delivery", request=request)
            return httpx.Response(202)

        async def publish(client, topic, event, payload):
            success = await realtime.publish_async(client, topic, event, payload)
            if not success and failure == "exception":
                raise RuntimeError("publish raised after delivery")
            return success

        monkeypatch.setattr(realtime, "get_settings", lambda: settings)
        monkeypatch.setattr(presence, "publish", publish)
        monkeypatch.setattr(
            presence,
            "create_async_client",
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(deliver)),
        )
        async with presence.publisher_lifespan() as worker:
            worker.reserve(room, 1).notify_committed()
            other = worker.reserve(other_room, 7)
            other.notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            stale = worker.reserve(room, 0)
            uncertain = worker.reserve(room, 2)
            uncertain.notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            expected = events(room, 1) + events(other_room, 7) + events(room, 2)
            assert received == expected
            confirmed = {
                (other_room, "presence.updated"): 7,
                (other_room, "room.count"): 7,
                (
                    room,
                    "room.count" if failed_event == "presence.updated" else "presence.updated",
                ): 2,
            }
            after_failure = worker._delivered.copy()
            assert worker._latest == {room: uncertain.revision, other_room: other.revision}
            stale.notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert received == expected

            worker.reserve(room, correction).notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            # Returning to 1 must correct subscribers; retrying 2 must deduplicate
            # the channel whose acknowledgement succeeded.
            expected += [
                item
                for item in events(room, correction)
                if correction == 1 or item[1] == failed_event
            ]
            assert received == expected
            assert after_failure == confirmed
            assert worker._delivered[(room, failed_event)] == correction
            worker.reserve(room, correction).notify_committed()
            worker.reserve(other_room, 7).notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert received == expected

    asyncio.run(scenario())


@pytest.fixture
def sent(monkeypatch):
    captured = []

    async def record(client, topic, event, payload):
        captured.append((topic, event, payload))
        return True

    monkeypatch.setattr(presence, "publish", record)
    return captured


def test_out_of_order_notifications_cannot_overwrite_delivered_newer_counts(sent):
    async def scenario():
        room = uuid4()
        async with presence.publisher_lifespan() as worker:
            updates = [worker.reserve(room, count) for count in range(50)]
            # Notifications can arrive on arbitrary request threads, after DB locks
            # have been released. Include an older notification after delivery too.
            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(lambda update: update.notify_committed(), reversed(updates)))
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert sent == events(room, 49)
            updates[0].notify_committed()
            await worker.wait_idle()
            assert sent == events(room, 49)
            worker.reserve(room, 0).notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert sent == events(room, 49, 0)

    asyncio.run(scenario())


def test_uncommitted_revision_does_not_suppress_an_older_commit(sent):
    async def scenario():
        room = uuid4()
        async with presence.publisher_lifespan() as worker:
            committed = worker.reserve(room, 1)
            worker.reserve(room, 2)  # transaction rolls back: no notification
            await worker.wait_idle()
            assert sent == []
            committed.notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert sent == events(room, 1)

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["exception", "http-failure"])
def test_channels_fail_independently_and_other_rooms_continue(monkeypatch, failure):
    async def scenario():
        first, second = uuid4(), uuid4()
        sent = []

        async def record(client, topic, event, payload):
            sent.append((topic, event, payload))
            if topic == f"room:{first}" and payload["count"] == 1:
                if failure == "exception":
                    raise RuntimeError("test transport failure")
                return False
            return True

        monkeypatch.setattr(presence, "publish", record)
        async with presence.publisher_lifespan() as worker:
            worker.reserve(first, 1).notify_committed()
            worker.reserve(second, 0).notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert sent == events(first, 1) + events(second, 0)
            # A coalesced return to 1 retries only the channel that failed.
            worker.reserve(first, 2).notify_committed()
            worker.reserve(first, 1).notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert sent[-1] == events(first, 1)[0]
            assert len(sent) == 5
            worker.reserve(first, 0).notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert sent[-2:] == events(first, 0)

    asyncio.run(scenario())


def test_worker_recovers_after_unexpected_delivery_error(monkeypatch, sent):
    async def scenario():
        original = presence.CountPublisher._send

        async def fail_once(self, client, update):
            if update.count == 1:
                raise RuntimeError("test worker error")
            await original(self, client, update)

        monkeypatch.setattr(presence.CountPublisher, "_send", fail_once)
        async with presence.publisher_lifespan() as worker:
            room = uuid4()
            worker.reserve(room, 1).notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            worker.reserve(room, 0).notify_committed()
            await asyncio.wait_for(worker.wait_idle(), 1)
            assert sent == events(room, 0)
            assert not worker.task.done()

    asyncio.run(scenario())


def test_lifespan_owns_one_worker_and_shutdown_cancels_stalled_io(monkeypatch):
    async def scenario():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        clients = []

        async def stall(client, *args):
            clients.append(client)
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        monkeypatch.setattr(presence, "publish", stall)
        app = create_app()
        async with app.router.lifespan_context(app):
            worker = app.state.presence_publisher
            with pytest.raises(RuntimeError, match="already owns"):
                async with presence.publisher_lifespan():
                    pass
            old = worker.reserve(uuid4(), 1)
            old.notify_committed()
            await asyncio.wait_for(entered.wait(), 1)
            # A short test deadline exercises bounded, cooperative cancellation.
            await asyncio.wait_for(worker.close(timeout=0.01), 1)
            assert cancelled.is_set()
            assert worker.task.done()
            assert clients[0].is_closed
            assert not worker._pending
            assert not worker._latest
            assert not worker._delivered
        assert presence._publisher is None
        async with presence.publisher_lifespan() as new:
            old.notify_committed()
            await new.wait_idle()
            assert not new._pending
        assert new.task.done()

    asyncio.run(scenario())
