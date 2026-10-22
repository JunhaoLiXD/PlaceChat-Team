"""Database access (PlaceChat Technical Design §8.3).

Synchronous SQLAlchemy 2.0 + psycopg 3, with a connection pool of 5.

Service functions that touch the database take the request's session as their first argument
(`db`), so one request can run several modules inside a single transaction.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Shared base for every table mapping, so all tables live in one `Base.metadata`."""


def normalize_database_url(url: str) -> str:
    """Supabase hands out postgresql://...; SQLAlchemy needs the psycopg 3 driver in the URL."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if url is None:
        raise RuntimeError("DATABASE_URL is not set. Copy backend/.env.example to backend/.env.")
    return create_engine(
        normalize_database_url(url.get_secret_value()),
        pool_size=5,
        max_overflow=0,
        pool_pre_ping=True,
    )


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    with _session_factory()() as session:
        yield session
