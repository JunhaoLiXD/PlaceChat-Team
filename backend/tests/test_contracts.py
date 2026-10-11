"""Contract tests that must keep passing after the real implementations replace the stubs."""

from app.modules.nicknames.service import generate_nickname


def test_generate_nickname_avoids_taken_names() -> None:
    taken: set[str] = set()
    for _ in range(30):
        nickname = generate_nickname(taken)
        assert nickname
        assert nickname not in taken
        taken.add(nickname)
