"""Rate limit contract, pipeline step 4 (PlaceChat Technical Design §5.2).

Owner: Yufei — PBI-19 (#23).
"""

from sqlalchemy.orm import Session as DbSession


def check_rate_limit(db: DbSession, session_id: str) -> None:
    """Raise RateLimited(retry_after) when the session is over the sending limit.

    Stub until PBI-19 (#23): allows every message.
    """
