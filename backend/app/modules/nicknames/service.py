"""Nickname contract (PlaceChat Technical Design §3.4).

Owner: Yufei — PBI-09 (#13), PBI-10 (#14).
"""


def generate_nickname(taken: set[str]) -> str:
    """Return a nickname that is not in `taken` (the room's reserved nicknames).

    Stub until PBI-09 (#13): returns "Guest 1", "Guest 2", ... so join can be built now.
    """
    number = 1
    while f"Guest {number}" in taken:
        number += 1
    return f"Guest {number}"
