"""The former name survives only in the plans dated before the rename and the plan performing it."""

from __future__ import annotations

import re

from tests.test_neutral import ROOT, tracked_files

# Split so this file does not match itself; separators are allowed so a hyphenated, spaced or
# wrapped spelling is caught as well as the contiguous one, and the initials are caught where
# they prefixed the wrapper's error tokens.
FORMER = re.compile("keel" + r"[\s_.-]*" + "line|" + r"(?-i:\bK" + r"L_[A-Z])", re.IGNORECASE)
RENAME_DAY = "2026-09-28"
RENAME_PLAN = f"{RENAME_DAY}-rename-stayfixed.md"
DATED = re.compile(r"\d{4}-\d{2}-\d{2}-[^/]+\.md")


def _historical(relative: str) -> bool:
    """A dated plan directly under `docs/plans/`, written before the rename or spelling it."""
    name = relative.removeprefix("docs/plans/")
    if name == relative or not DATED.fullmatch(name):
        return False
    return name < RENAME_DAY or name == RENAME_PLAN


def test_the_former_name_survives_only_in_the_historical_plans() -> None:
    # Watched red on eight planted files: a path carrying the name, a file mentioning it, a
    # hyphenated and a line-wrapped spelling, an error token under the initials, and three plans
    # outside the exemption: undated (`1-notes.md`, which sorts before the date), nested
    # (`2025/old.md`) and dated the rename day.
    hits = [
        relative
        for path in tracked_files()
        if not _historical(relative := path.relative_to(ROOT).as_posix())
        and (
            FORMER.search(relative)
            or FORMER.search(path.read_text(encoding="utf-8", errors="replace"))
        )
    ]
    assert hits == [], hits
