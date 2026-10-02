"""Pluggable strategies for choosing which queued photo to post next."""

from __future__ import annotations

import os
from typing import Callable

# Each strategy receives the list of candidate image file dicts (Drive API
# file resources, each with at least "id", "name", "createdTime") and
# returns the single file dict to post next.
DriveFile = dict
SelectionStrategy = Callable[[list[DriveFile]], DriveFile]


def _oldest_first(files: list[DriveFile]) -> DriveFile:
    return min(files, key=lambda f: f["createdTime"])


def _alphabetical(files: list[DriveFile]) -> DriveFile:
    return min(files, key=lambda f: f["name"])


def _random(files: list[DriveFile]) -> DriveFile:
    import random

    return random.choice(files)


SELECTION_STRATEGIES: dict[str, SelectionStrategy] = {
    "oldest_first": _oldest_first,
    "alphabetical": _alphabetical,
    "random": _random,
}

DEFAULT_STRATEGY = "oldest_first"


def get_active_strategy() -> SelectionStrategy:
    name = os.environ.get("SELECTION_STRATEGY", DEFAULT_STRATEGY)
    try:
        return SELECTION_STRATEGIES[name]
    except KeyError:
        raise ValueError(
            f"Unknown SELECTION_STRATEGY {name!r}; valid options: "
            f"{sorted(SELECTION_STRATEGIES)}"
        ) from None


def choose_next(files: list[DriveFile]) -> DriveFile:
    if not files:
        raise ValueError("No candidate files to choose from")
    return get_active_strategy()(files)
