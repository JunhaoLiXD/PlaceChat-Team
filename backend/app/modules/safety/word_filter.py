"""Word filter contract, pipeline step 5 (PlaceChat Technical Design §2.2 D3).

Owner: Yufei — PBI-36 (Sprint 2).
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.safety.models import BlockedWord


def filter_text(db: Session, text: str) -> str:
    """Return `text` with every blocked word masked by asterisks.

    Words are loaded for each message so changes take effect without redeploying.
    """
    words = db.scalars(select(BlockedWord.word)).all()
    if not words:
        return text

    pattern = re.compile(
        rf"\b(?:{'|'.join(re.escape(word) for word in words)})\b",
        re.IGNORECASE,
    )
    return pattern.sub(lambda match: "*" * len(match.group()), text)
