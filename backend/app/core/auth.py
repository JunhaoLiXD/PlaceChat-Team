"""Authentication contracts (PlaceChat Technical Design §3.4, §6).

Owner: Zhijie — PBI-06 (#10), PBI-21 (#25).

Student tokens are verified against the configured project's cached ES256 JWKS.
Administrators must also be non-anonymous and present in the database allow-list.
"""

from dataclasses import dataclass
from functools import lru_cache
from math import isfinite
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient
from sqlalchemy.orm import Session as DbSession

from app.core import auth_repository
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import Forbidden, Unauthenticated


@dataclass(frozen=True)
class Session:
    """The caller's identity. `id` is the Supabase user id (the access token's `sub`)."""

    id: str
    is_anonymous: bool


@dataclass(frozen=True)
class Admin:
    user_id: str


@lru_cache(maxsize=1)
def get_jwks_client(supabase_url: str) -> PyJWKClient:
    """Reuse PyJWT's expiring JWKS cache; never trust a key URL supplied by a token."""
    return PyJWKClient(
        f"{supabase_url}/auth/v1/.well-known/jwks.json",
        cache_jwk_set=True,
        timeout=10,
    )


def get_current_session(request: Request) -> Session:
    """FastAPI dependency: verify the Bearer token and return the caller's session.

    Raises Unauthenticated (401) when the token is missing, invalid, or expired.
    """
    authorization = request.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise Unauthenticated()

    token = parts[1]
    supabase_url = get_settings().supabase_url.rstrip("/")
    if not supabase_url:
        raise Unauthenticated()

    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "ES256" or not isinstance(header.get("kid"), str):
            raise Unauthenticated()
        if not header["kid"]:
            raise Unauthenticated()

        signing_key = get_jwks_client(supabase_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
            issuer=f"{supabase_url}/auth/v1",
            options={
                "require": ["sub", "exp", "aud", "iss", "is_anonymous"],
                "strict_aud": True,
            },
        )
        # PyJWT accepts numeric strings for NumericDate; require a JSON number instead.
        expiry = claims["exp"]
        if type(expiry) not in (int, float) or (isinstance(expiry, float) and not isfinite(expiry)):
            raise Unauthenticated()
        if not isinstance(claims["sub"], str) or not claims["sub"].strip():
            raise Unauthenticated()
        if type(claims["is_anonymous"]) is not bool:
            raise Unauthenticated()
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
        raise Unauthenticated() from None

    return Session(id=claims["sub"], is_anonymous=claims["is_anonymous"])


def require_admin(
    current: Annotated[Session, Depends(get_current_session)],
    db: Annotated[DbSession, Depends(get_db)],
) -> Admin:
    """FastAPI dependency for /admin routes.

    Raises Unauthenticated (401) without a token, Forbidden (403) for anyone who is anonymous or
    not listed in admin_users.
    """
    if current.is_anonymous:
        raise Forbidden()
    try:
        user_id = UUID(current.id)
    except ValueError:
        raise Forbidden() from None
    if not auth_repository.is_admin_user(db, user_id):
        raise Forbidden()
    return Admin(user_id=current.id)
