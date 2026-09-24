"""Stack profiles: data under this package, read the way an installed wheel can read it.

Each directory here that holds a `profile.toml` is one profile, and its `rules.md` is required
beside it. `shipped()` is the listing `scaffold.validate_sources` checks `[keelline] profile`
against, and `load_profile` is the one reader. A name outside the listing is refused with fixed
text: the name arrives from a repository's `keelline.toml`, so it is never printed.
"""

from __future__ import annotations

import tomllib
from importlib import resources
from importlib.resources.abc import Traversable

from keelline.config.schema import PROJECT_NAME
from keelline.profiles.evaluate import Outcome, detects, evaluate
from keelline.profiles.model import Check, Profile, ProfileError, parse

PROFILE_FILE = "profile.toml"
RULES_FILE = "rules.md"
NOT_SHIPPED = "[keelline] profile names no profile this Keelline ships"

__all__ = [
    "PROFILE_FILE",
    "RULES_FILE",
    "Check",
    "Outcome",
    "Profile",
    "ProfileError",
    "detects",
    "evaluate",
    "load_profile",
    "shipped",
]


def _source(source: Traversable | None) -> Traversable:
    return source if source is not None else resources.files(__package__)


def shipped(*, source: Traversable | None = None) -> tuple[str, ...]:
    root = _source(source)
    return tuple(
        sorted(
            entry.name
            for entry in root.iterdir()
            if entry.is_dir()
            and PROJECT_NAME.match(entry.name)
            and entry.joinpath(PROFILE_FILE).is_file()
        )
    )


def load_profile(name: str, *, source: Traversable | None = None) -> Profile:
    if name not in shipped(source=source):
        raise ProfileError(NOT_SHIPPED)
    directory = _source(source).joinpath(name)
    try:
        document = tomllib.loads(directory.joinpath(PROFILE_FILE).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{name}/{PROFILE_FILE} is not valid TOML: {exc}") from None
    rules = directory.joinpath(RULES_FILE)
    if not rules.is_file():
        raise ProfileError(f"{name}/{RULES_FILE} is missing")
    return parse(name, document, rules.read_text(encoding="utf-8"))
