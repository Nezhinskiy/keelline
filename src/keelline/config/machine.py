"""Where the machine-level configuration lives (§5.4); the file is optional.

**Both variables that can name this file are gated, and for one reason.** A committed
`.claude/settings.json` may carry an `env` block, which applies without a trust prompt in a
non-interactive session, so a repository able to redirect this path would declare its own
overlay root and its own pre-recorded trust hash — the two anchors §9.1 and §9.4 rest on.

`KEELLINE_CONFIG` was gated and `XDG_CONFIG_HOME` was not, which left the gate worth nothing:
the two variables reach the same file, and the second one costs a repository exactly one extra
path segment (`<dir>/keelline/config.toml` rather than the file itself). Gating one of a pair
of equivalent inputs is not a partial defence, it is a redirect with a longer name, so the
rule is now the variable-independent one: **in a non-interactive session this file is
`~/.config/keelline/config.toml` and nothing else.**

That is the XDG specification's own answer for an unset `XDG_CONFIG_HOME`, so a machine owner
who sets one really does lose it on the hook path rather than getting a wrong answer quietly —
`keelline doctor` is where that belongs once it exists. The cost is bounded and the exposure it
replaces was not: `permitted_roots`, `trust.json` and the overlay anchor were all selectable by
a file the clone ships.

A caller that knows it is a hook, the MCP server or a `keelline gate` run says
`interactive=False` rather than relying on the terminal check — `config.loader.load` takes the
same keyword for exactly that reason.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

DEFAULT_CONFIG_DIR = Path(".config")


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
    honoured = override_is_honoured(interactive)
    explicit = env.get("KEELLINE_CONFIG") if honoured else None
    if explicit:
        return Path(explicit)
    base = (env.get("XDG_CONFIG_HOME") if honoured else None) or str(
        Path.home() / DEFAULT_CONFIG_DIR
    )
    return Path(base) / "keelline" / "config.toml"
