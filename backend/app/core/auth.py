"""Authentication contracts (PlaceChat Technical Design §3.4, §6).

Owner: Zhijie — PBI-06 (#10), PBI-21 (#25).

Until these are implemented they raise NotImplementedError, which fails closed (HTTP 500).
In tests, replace them with app.dependency_overrides[get_current_session] = lambda: Session(...).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Session:
    """The caller's identity. `id` is the Supabase user id (the access token's `sub`)."""

    id: str
    is_anonymous: bool


@dataclass(frozen=True)
class Admin:
    user_id: str


def get_current_session() -> Session:
    """FastAPI dependency: verify the Bearer token and return the caller's session.

    Raises Unauthenticated (401) when the token is missing, invalid, or expired.
    """
    raise NotImplementedError("get_current_session is implemented in PBI-06 (#10)")


def require_admin() -> Admin:
    """FastAPI dependency for /admin routes.

    Raises Unauthenticated (401) without a token, Forbidden (403) for anyone who is anonymous or
    not listed in admin_users.
    """
    raise NotImplementedError("require_admin is implemented in PBI-21 (#25)")
