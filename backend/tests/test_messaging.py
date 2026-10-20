import pytest

from app.core.errors import ValidationFailed
from app.modules.messaging.service import validate_message


def test_validate_message_rejects_empty_text() -> None:
    with pytest.raises(ValidationFailed, match="cannot be empty"):
        validate_message("")


def test_validate_message_rejects_whitespace_only_text() -> None:
    with pytest.raises(ValidationFailed, match="cannot be empty"):
        validate_message(" \t\n ")


def test_validate_message_trims_surrounding_whitespace() -> None:
    assert validate_message("  hello  ") == "hello"


def test_validate_message_accepts_one_character() -> None:
    assert validate_message("a") == "a"


def test_validate_message_accepts_500_characters() -> None:
    text = "a" * 500

    assert validate_message(text) == text


def test_validate_message_rejects_501_characters() -> None:
    with pytest.raises(ValidationFailed, match="500 characters or fewer"):
        validate_message("a" * 501)


def test_validate_message_accepts_emoji() -> None:
    assert validate_message("👋") == "👋"
