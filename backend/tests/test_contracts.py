"""Contract tests that must keep passing after the real implementations replace the stubs."""

import re

import pytest

import app.modules.nicknames.service as nickname_service
from app.modules.nicknames.service import (
    ADJECTIVES,
    ANIMALS,
    generate_nickname,
)


def test_generate_nickname_avoids_taken_names() -> None:
    taken: set[str] = set()
    for _ in range(30):
        nickname = generate_nickname(taken)
        assert nickname
        assert nickname not in taken
        taken.add(nickname)


def test_generate_nickname_is_an_adjective_and_animal() -> None:
    nickname = generate_nickname(set())

    adjective, animal = nickname.split()
    assert adjective in ADJECTIVES
    assert animal in ANIMALS
    assert nickname == nickname.title()


def test_generate_nickname_numbers_only_when_all_base_names_are_taken() -> None:
    taken = {f"{adjective} {animal}" for adjective in ADJECTIVES for animal in ANIMALS}

    nickname = generate_nickname(taken)

    assert re.fullmatch(r"[A-Z][a-z]+ [A-Z][a-z]+ 1", nickname)
    assert nickname not in taken


def test_generate_nickname_uses_the_only_remaining_base_name() -> None:
    missing = "Zesty Zebra"
    taken = set(nickname_service._COMBINATIONS) - {missing}

    assert generate_nickname(taken) == missing


def test_generate_nickname_skips_taken_numbered_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = nickname_service._COMBINATIONS[0]
    taken = set(nickname_service._COMBINATIONS)
    taken.update(f"{base} {number}" for number in (1, 2, 4))
    monkeypatch.setattr(nickname_service, "choice", lambda values: base)

    assert generate_nickname(taken) == f"{base} 3"


def test_generate_nickname_repeated_numbered_allocations_are_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = nickname_service._COMBINATIONS[0]
    taken = set(nickname_service._COMBINATIONS)
    monkeypatch.setattr(nickname_service, "choice", lambda values: base)

    generated = []
    for _ in range(5):
        nickname = generate_nickname(taken)
        generated.append(nickname)
        taken.add(nickname)

    assert generated == [f"{base} {number}" for number in range(1, 6)]
    assert len(taken) == len(nickname_service._COMBINATIONS) + 5
