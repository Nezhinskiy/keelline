"""The project has one name, and the former one survives only in the historical plans.

The rename to stayfixed happened before the first release, so nothing a user can install ever
carried the former name, and nothing tracked should carry it now: not a module path, not an
environment variable, not a sentence. The plans written before the rename are the record of the
work as it was argued and keep their wording, and so does the plan that spells the mapping.
The former name is assembled from two halves so this file does not match itself.
"""

from __future__ import annotations

import re

from tests.test_neutral import ROOT, tracked_files

FORMER = "keel" + "line"
PATTERN = re.compile(FORMER, re.IGNORECASE)

# Plans dated before the rename, the plan that performs it, and this file.
RENAME_DAY = "2026-09-28"


def _exempt(relative: str) -> bool:
    if relative == "tests/test_name.py":
        return True
    if relative.startswith("docs/plans/") and relative != "docs/plans/README.md":
        name = relative.removeprefix("docs/plans/")
        return name[:10] < RENAME_DAY or name == f"{RENAME_DAY}-rename-stayfixed.md"
    return False


def test_no_tracked_path_carries_the_former_name() -> None:
    hits = [
        str(p.relative_to(ROOT))
        for p in tracked_files()
        if PATTERN.search(str(p.relative_to(ROOT))) and not _exempt(str(p.relative_to(ROOT)))
    ]
    assert hits == [], f"{len(hits)} path(s) still carry the former name, first: {hits[:5]}"


def test_no_tracked_file_mentions_the_former_name() -> None:
    hits: list[str] = []
    for path in tracked_files():
        relative = str(path.relative_to(ROOT))
        if _exempt(relative):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if PATTERN.search(text):
            hits.append(relative)
    assert hits == [], f"{len(hits)} file(s) still mention the former name, first: {hits[:5]}"
