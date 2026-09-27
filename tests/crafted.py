"""A name a repository can commit, and the check that it never reaches a printed line raw.

One spelling for every test that crafts one: a line break, a line the Actions runner reads as a
workflow command, and a terminal escape that clears the screen.
"""

from __future__ import annotations

CRAFTED = "x\n::error::forged\x1b[2J"
# The same name as a TOML basic string spells it, which decodes back to `CRAFTED`.
CRAFTED_TOML = "x\\n::error::forged\\u001b[2J"


def assert_never_raw(*streams: str) -> None:
    """No stream carries an escape byte or a line that starts a workflow command. Every stream a
    command wrote is passed, so a leak moved from stdout to stderr is still caught."""
    for text in streams:
        assert "\x1b" not in text
        assert "\n::error::" not in text and not text.startswith("::error::")
