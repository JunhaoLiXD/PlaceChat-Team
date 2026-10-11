"""Temporary block contract, pipeline step 2 (PlaceChat Technical Design §3.4).

Owner: Zhijie — PBI-42 (Sprint 2).
"""

from sqlalchemy.orm import Session as DbSession


def check_not_blocked(db: DbSession, session_id: str) -> None:
    """Raise Blocked(until) when the session has an active block.

    Stub until PBI-42 (Sprint 2): nobody is blocked.
    """
