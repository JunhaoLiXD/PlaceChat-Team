"""Nickname generation for temporary, room-local participant names."""

from itertools import product
from secrets import choice

ADJECTIVES = (
    "Bright",
    "Calm",
    "Clever",
    "Cozy",
    "Daring",
    "Eager",
    "Gentle",
    "Glad",
    "Golden",
    "Happy",
    "Kind",
    "Lively",
    "Lucky",
    "Mellow",
    "Merry",
    "Mighty",
    "Neat",
    "Nimble",
    "Peaceful",
    "Playful",
    "Polite",
    "Proud",
    "Quiet",
    "Rapid",
    "Ready",
    "Silly",
    "Smooth",
    "Snappy",
    "Sunny",
    "Swift",
    "Tender",
    "Thoughtful",
    "Tiny",
    "Upbeat",
    "Warm",
    "Witty",
    "Wise",
    "Zesty",
    "Breezy",
    "Cheery",
)

ANIMALS = (
    "Badger",
    "Beaver",
    "Bison",
    "Bluebird",
    "Bunny",
    "Capybara",
    "Dolphin",
    "Duck",
    "Eagle",
    "Falcon",
    "Fawn",
    "Fox",
    "Gecko",
    "Gopher",
    "Hare",
    "Hedgehog",
    "Heron",
    "Koala",
    "Lemur",
    "Lion",
    "Llama",
    "Otter",
    "Panda",
    "Parrot",
    "Penguin",
    "Puffin",
    "Rabbit",
    "Raccoon",
    "Robin",
    "Seal",
    "Sparrow",
    "Squirrel",
    "Tern",
    "Tiger",
    "Turtle",
    "Walrus",
    "Whale",
    "Wombat",
    "Yak",
    "Zebra",
)

_COMBINATIONS = tuple(
    f"{adjective} {animal}" for adjective, animal in product(ADJECTIVES, ANIMALS)
)


def generate_nickname(taken: set[str]) -> str:
    """Return a random available adjective-and-animal nickname.

    The base pool is 40 x 40. Numbered names are used only after every base
    combination has been reserved.
    """
    available = tuple(nickname for nickname in _COMBINATIONS if nickname not in taken)
    if available:
        return choice(available)

    base = choice(_COMBINATIONS)
    number = 1
    while f"{base} {number}" in taken:
        number += 1
    return f"{base} {number}"
