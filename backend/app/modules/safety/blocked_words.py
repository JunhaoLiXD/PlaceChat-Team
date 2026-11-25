"""Maintain the blocked-word list (PlaceChat Technical Design §2.2 D3, §7.1).

Owner: Junhao — PBI-37 (#72).

`filter_text` reads the list for every message, so a change applies to the next message
without a redeploy.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app.core.errors import ValidationFailed
from app.modules.safety.models import BlockedWord


def list_words(db: DbSession) -> list[BlockedWord]:
    return list(db.scalars(select(BlockedWord).order_by(BlockedWord.word)))


def add_word(db: DbSession, word: str) -> BlockedWord:
    """Add one lowercase word. A word already on the list is rejected, not duplicated."""
    if _exists(db, word):
        raise _duplicate(word)
    blocked = BlockedWord(id=uuid4(), word=word, created_at=datetime.now(UTC))
    db.add(blocked)
    try:
        db.commit()
    except IntegrityError:
        # Another admin added the same word at the same moment, or the database
        # rejected the value (its own lower() can differ from Python's for rare letters).
        db.rollback()
        if _exists(db, word):
            raise _duplicate(word) from None
        raise ValidationFailed("This word can't be added to the list.") from None
    db.refresh(blocked)
    return blocked


def delete_word(db: DbSession, word_id: UUID) -> None:
    """Remove a word. Removing a word that is already gone is not an error."""
    blocked = db.get(BlockedWord, word_id)
    if blocked is not None:
        db.delete(blocked)
        db.commit()


def _exists(db: DbSession, word: str) -> bool:
    return db.scalar(select(BlockedWord.id).where(BlockedWord.word == word)) is not None


def _duplicate(word: str) -> ValidationFailed:
    return ValidationFailed(f'"{word}" is already on the blocked-word list.')
