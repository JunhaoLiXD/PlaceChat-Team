"""Realtime publisher (PlaceChat Technical Design §6.5). Owner: Junhao — PBI-15 (#19).

FastAPI is the only sender. It calls Realtime's REST broadcast endpoint with the secret key;
browsers subscribe to private channels and can only receive.
"""

import asyncio
import logging
from functools import lru_cache
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Keep a slow Realtime call from holding up the request that triggered it.
TIMEOUT_SECONDS = 3.0


@lru_cache
def get_http_client() -> httpx.Client:
    """One pooled client, so repeated broadcasts reuse the TLS connection."""
    return httpx.Client(timeout=TIMEOUT_SECONDS)


def broadcast_url(supabase_url: str, topic: str, event: str) -> str:
    topic_path = quote(topic, safe="")
    event_path = quote(event, safe="")
    return f"{supabase_url.rstrip('/')}/realtime/v1/api/broadcast/{topic_path}/events/{event_path}"


def _request(topic: str, event: str, payload: dict[str, Any]) -> httpx.Request | None:
    settings = get_settings()
    if not settings.supabase_url or settings.supabase_secret_key is None:
        logger.warning("Realtime is not configured; dropped %s %s", topic, event)
        return None
    return httpx.Request(
        "POST",
        broadcast_url(settings.supabase_url, topic, event),
        params={"private": "true"},
        headers={"apikey": settings.supabase_secret_key.get_secret_value()},
        json=payload,
    )


def publish(topic: str, event: str, payload: dict[str, Any]) -> None:
    """Store first, then broadcast privately; failures never undo a commit (§4)."""
    request = _request(topic, event, payload)
    if request is None:
        return

    try:
        response = get_http_client().send(request)
        response.raise_for_status()
    except httpx.HTTPError as error:
        logger.error("Realtime publish failed for %s %s: %r", topic, event, error)


def create_async_client() -> httpx.AsyncClient:
    """Owned and closed by the count publisher, separate from message requests."""
    return httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
    )


async def publish_async(
    client: httpx.AsyncClient, topic: str, event: str, payload: dict[str, Any]
) -> bool:
    request = _request(topic, event, payload)
    if request is None:
        return False
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            response = await client.send(request)
            response.raise_for_status()
    except (httpx.HTTPError, TimeoutError) as error:
        logger.error("Realtime publish failed for %s %s: %r", topic, event, error)
        return False
    return True
