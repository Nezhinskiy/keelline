"""Presets ship inside the package so an installed wheel can read them."""

from __future__ import annotations

import tomllib
from importlib import resources
from typing import Any

from keelline.errors import Failure


def load_preset(name: str) -> dict[str, Any]:
    if not name.replace("-", "").replace("_", "").isalnum():
        raise Failure(f"preset name {name!r} is not a plain identifier")
    resource = resources.files(__package__).joinpath(f"{name}.toml")
    if not resource.is_file():
        raise Failure(f"preset {name!r} is not shipped with this version of Keelline")
    return tomllib.loads(resource.read_text(encoding="utf-8"))
