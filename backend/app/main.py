import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.modules.rooms.sweeper import run_presence_sweeper


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    task = asyncio.create_task(run_presence_sweeper(stop), name="presence-sweeper")
    try:
        yield
    finally:
        # Wake an idle task immediately; allow an in-flight worker to finish and close
        # its session instead of abandoning synchronous work during cancellation.
        stop.set()
        await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PlaceChat API", version="0.1.0", lifespan=lifespan)
    # The browser sends a Bearer token, not cookies, so credentials stay off.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
