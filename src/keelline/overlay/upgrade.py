"""Refresh an overlay after a release, and name the two files nobody may refresh silently.

The refresh itself is C2's, unchanged: an untouched skeleton file is updated, a hand-edited one
is skipped and named, and the oracle is the digest the manifest recorded. An overlay is where
the owner's own rules live, so a silent overwrite here destroys the only copy of something —
which is exactly why this lane calls the engine rather than reimplementing the rule.

**Why a wrapper type rather than a bare `Plan`.** §6.1 gives two files an exception to the hash
rule: `common/claude/permissions.json` and `common/claude/hooks.json` are diffed and asked about
*regardless of hash*, because they are the two that can grant capability and a hash match is not
consent for those. C2's `Plan` has no verb for "needs a decision" and C2 is frozen for this plan,
so the answer is a type *around* the plan rather than a new `Verb` inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from keelline.config.loader import preset_defaults
from keelline.overlay.layout import CAPABILITY_FILES
from keelline.overlay.template import templates
from keelline.scaffold import Plan, apply, plan


@dataclass(frozen=True)
class OverlayUpgrade:
    plan: Plan
    decisions: tuple[str, ...]


def upgrade(root: Path, *, dry_run: bool) -> OverlayUpgrade:
    """What a release would change in this overlay, and what it must ask about first.

    `project.name` is the instance's directory name and goes nowhere: the engine reads
    `keelline.profile` and `artifacts.local` out of a `Config` and nothing else. It is passed
    because a `Config` has to be complete, not because an overlay is a project.
    """
    shipped = templates()
    planned = plan(root, preset_defaults(root.name), shipped)
    if not dry_run:
        apply(root, planned)
    decisions = tuple(item.id for item in shipped if item.id in CAPABILITY_FILES)
    return OverlayUpgrade(planned, decisions)
