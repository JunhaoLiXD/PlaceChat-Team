"""Blocked-word filtering tests."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.db import Base
from app.modules.safety.models import BlockedWord
from app.modules.safety.word_filter import filter_text


def test_filter_masks_blocked_words_case_insensitively() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(BlockedWord(id=uuid4(), word="darn", created_at=datetime.now(UTC)))
        db.commit()

        assert filter_text(db, "DARN, darned, and darn!") == "****, darned, and ****!"

    engine.dispose()


def test_filter_leaves_text_without_blocked_words_unchanged() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(BlockedWord(id=uuid4(), word="darn", created_at=datetime.now(UTC)))
        db.commit()

        text = "A calm message."
        assert filter_text(db, text) == text

    engine.dispose()
