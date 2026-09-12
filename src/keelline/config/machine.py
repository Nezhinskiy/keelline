"""Where the machine-level configuration lives (§5.4); the file is optional.

`KEELLINE_CONFIG` is honoured only from an interactive shell. A committed
`.claude/settings.json` may carry an `env` block, which applies without a trust prompt in a
non-interactive session, so a repository able to redirect this variable would declare its own
overlay root and its own pre-recorded trust hash — the two anchors §9.1 and §9.4 rest on. The
default is therefore to ignore it, and a caller that knows it is a hook, the MCP server or a
`--gate` run says `interactive=False` rather than relying on the terminal check.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path


def override_is_honoured(interactive: bool | None = None) -> bool:
    if interactive is not None:
        return interactive
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def machine_config_path(
    env: Mapping[str, str] | None = None, *, interactive: bool | None = None
) -> Path:
    env = os.environ if env is None else env
    explicit = env.get("KEELLINE_CONFIG") if override_is_honoured(interactive) else None
    if explicit:
        return Path(explicit)
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "keelline" / "config.toml"
