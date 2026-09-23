"""Presets ship inside the package so an installed wheel can read them."""

from __future__ import annotations

import tomllib
from importlib import resources
from typing import Any

from keelline.errors import Failure

# The rule a preset name is held to, in words, for the refusal a person reads.
NAME_RULE = "letters, digits, `-` and `_`"


def shipped_presets() -> list[str]:
    """The preset names this build carries — Keelline's own vocabulary, and so safe to print."""
    return sorted(
        entry.name.removesuffix(".toml")
        for entry in resources.files(__package__).iterdir()
        if entry.name.endswith(".toml")
    )


def load_preset(name: str, *, key: str = "[keelline] preset") -> dict[str, Any]:
    """The named preset's table, or a refusal that names `key` and never `name`.

    `name` is repository-authored when it comes from a clone's `keelline.toml`, and neither
    refusal may carry it: the first runs exactly for a value that failed the identifier check,
    so it can hold ESC and line breaks, and both reach a terminal and a model through the skills'
    relay. This is `config.loader._enum`'s ruling. The `setup --preset` path passes `key` and is
    held to the same rule rather than given an exception: the person who typed the value has it
    on their own screen, and the list of shipped presets is what they need to fix it.
    """
    if not name.replace("-", "").replace("_", "").isalnum():
        raise Failure(f"{key} is not a plain identifier ({NAME_RULE}); {_available()}")
    resource = resources.files(__package__).joinpath(f"{name}.toml")
    if not resource.is_file():
        raise Failure(
            f"{key} names a preset this version of Keelline does not ship; {_available()}"
        )
    return tomllib.loads(resource.read_text(encoding="utf-8"))


def _available() -> str:
    return f"available: {', '.join(shipped_presets()) or 'none'}"
