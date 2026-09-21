"""What an overlay declares it needs, and whether a running Keelline meets it (P6).

The declaration is read in the one form the template ships, `>=X.Y.Z`, and no other: a caller
that wants a different comparison has a different question, and answering it here would grow
a parser nothing has asked for yet. `requires_of`'s return value is the normalised string a
caller may print — it is what the overlay itself declared, stripped, not a value this module
built out of parts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from keelline.overlay.layout import PLUGIN_MANIFEST

_FLOOR = re.compile(r"^>=(\d+)\.(\d+)\.(\d+)$")
_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def requires_of(root: Path) -> str | None:
    """The `keelline.requires` string an overlay's manifest declares, stripped.

    `None` when the manifest is absent, unreadable, or does not carry a non-empty string —
    every one of those is "nothing declared", and none of them is this reader's business to
    tell apart.
    """
    path = root / PLUGIN_MANIFEST
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    head = raw.get("keelline")
    value = head.get("requires") if isinstance(head, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def satisfies(spec: str, version: str) -> bool | None:
    """`True`/`False` for `>=X.Y.Z` against an `X.Y.Z[...]` version, compared as integer tuples.

    `None` for any other spec shape or a version this reader cannot parse — a caller that gets
    `None` back has an unreadable declaration, not a false one.
    """
    floor = _FLOOR.match(spec)
    running = _VERSION.match(version)
    if floor is None or running is None:
        return None
    return tuple(int(part) for part in running.groups()) >= tuple(
        int(part) for part in floor.groups()
    )
