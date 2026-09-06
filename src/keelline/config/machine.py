"""Where the machine-level configuration lives (§5.4); the file is optional."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def machine_config_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    explicit = env.get("KEELLINE_CONFIG")
    if explicit:
        return Path(explicit)
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keelline" / "config.toml"
