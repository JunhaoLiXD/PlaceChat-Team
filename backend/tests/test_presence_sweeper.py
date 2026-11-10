"""Lifespan and worker tests use fakes only: never the application's DATABASE_URL."""

import asyncio
from contextlib import contextmanager
from threading import Event, get_ident
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.modules.rooms import service, sweeper

# The autouse fixture disables background I/O in all ordinary request tests. Keep
# the real iteration here so these tests can exercise it with explicit fakes.
sweep_presence = sweeper.sweep_presence


def test_iteration_closes_sessions_and_continues_after_one_room_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    rooms = [uuid4(), uuid4(), uuid4()]
    sessions: list[Mock] = []
    closed: list[Mock] = []
    processed = []

    @contextmanager
    def database():
        db = Mock(spec=Session)
        sessions.append(db)
        try:
            yield db
        finally:
            closed.append(db)

    def discover(db):
        assert sessions == [db]
        return rooms

    def process(db, room_id):
        assert closed == sessions[:-1]
        assert db is sessions[-1]
        processed.append(room_id)
        if room_id == rooms[1]:
            raise RuntimeError("test room failure")

    monkeypatch.setattr(sweeper, "create_session", database)
    monkeypatch.setattr(sweeper.repository, "active_room_ids", discover)
    monkeypatch.setattr(service, "sweep_room_presence", process)
    sweep_presence()
    assert processed == rooms
    assert len(sessions) == 4
    assert closed == sessions
    assert "Presence sweep failed for room" in caplog.text


def test_failed_iteration_is_retried_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    threads = []
    monkeypatch.setattr(
        sweeper, "get_settings", lambda: Settings(_env_file=None, sweeper_interval_seconds=1)
    )

    async def scenario():
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        loop_thread = get_ident()

        def iteration():
            threads.append(get_ident())
            if len(threads) == 1:
                raise RuntimeError("test discovery failure")
            loop.call_soon_threadsafe(stop.set)

        monkeypatch.setattr(sweeper, "sweep_presence", iteration)
        async with asyncio.timeout(3):
            await sweeper.run_presence_sweeper(stop)
        assert len(threads) == 2
        assert all(thread != loop_thread for thread in threads)

    asyncio.run(scenario())
    assert "Presence sweep iteration failed" in caplog.text


def test_lifespan_starts_one_sweeper_and_wakes_it_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = Event()
    calls = []

    def iteration():
        calls.append(get_ident())
        called.set()

    monkeypatch.setattr(sweeper, "sweep_presence", iteration)
    monkeypatch.setattr(
        sweeper, "get_settings", lambda: Settings(_env_file=None, sweeper_interval_seconds=10)
    )

    async def scenario():
        app = create_app()
        async with app.router.lifespan_context(app):
            assert await asyncio.to_thread(called.wait, 2)
            tasks = [t for t in asyncio.all_tasks() if t.get_name() == "presence-sweeper"]
            assert len(tasks) == 1
        assert tasks[0].done()
        assert len(calls) == 1

    asyncio.run(scenario())


def test_shutdown_waits_for_inflight_worker_without_blocking_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, release, finished = Event(), Event(), Event()

    def iteration():
        started.set()
        assert release.wait(3), "Test did not release the worker"
        finished.set()

    monkeypatch.setattr(sweeper, "sweep_presence", iteration)

    async def scenario():
        app = create_app()
        context = app.router.lifespan_context(app)
        await context.__aenter__()
        shutdown = None
        try:
            assert await asyncio.to_thread(started.wait, 2)
            shutdown = asyncio.create_task(context.__aexit__(None, None, None))
            await asyncio.sleep(0.01)
            assert not shutdown.done()
            assert not finished.is_set()
        finally:
            release.set()
            if shutdown is None:
                await context.__aexit__(None, None, None)
            else:
                await asyncio.wait_for(shutdown, timeout=2)
        assert finished.is_set()

    asyncio.run(scenario())
