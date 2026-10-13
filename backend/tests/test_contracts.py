"""Contract tests that must keep passing after the real implementations replace the stubs."""

import re

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
