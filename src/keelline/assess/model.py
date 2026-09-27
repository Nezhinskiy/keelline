"""One item of the inventory: what a gate or a probe found, and what to do about it.

`where` names what was found — a path the repository chose, a sha, or the probe's own words —
and goes to the machine-readable output only; no summary prints it. It is capped, so one
neglected tree cannot grow the inventory without bound, and `count` stays whole, because the
number is what a person acts on.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from keelline.findings import Severity

WHERE_CAP = 200  # labels kept per item; `count` stays whole


@dataclass(frozen=True)
class Item:
    probe: str  # the gate or probe that found it
    rule: str
    principle: int | None
    severity: Severity
    remedy: str
    where: tuple[str, ...]  # labels, capped at WHERE_CAP; never printed by a summary
    count: int  # how many there were, never capped


def item(
    probe: str,
    rule: str,
    principle: int | None,
    severity: Severity,
    remedy: str,
    where: Sequence[str],
    count: int | None = None,
) -> Item:
    """The one constructor: `where` capped at `WHERE_CAP`, `count` its whole length unless given."""
    return Item(
        probe,
        rule,
        principle,
        severity,
        remedy,
        tuple(where[:WHERE_CAP]),
        len(where) if count is None else count,
    )
