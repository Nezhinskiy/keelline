"""The smoke fixture as a repository with a change to judge: two commits, judged from the first.

Against `HEAD` itself `plan` would diff `HEAD...HEAD` and `commit` would read `HEAD..HEAD`, so
both would pass by reading nothing; against `BASE` each has something to read.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from keelline.config.loader import preset_defaults
from tests.gitfixture import git

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "smoke-project"
# The fixture sets no `[paths]`, so its plans sit where the preset puts them.
PLAN = Path(preset_defaults("smoke").paths.plans) / "2026-09-19-the-fixtures-own-plan.md"
BASE = "HEAD~1"


def smoke_repo(tmp_path: Path) -> Path:
    """Two commits: everything but the fixture's own plan, then the plan. Against `BASE`,
    `plan` has a plan to lint and `commit` a range to read, so neither passes by reading
    nothing."""
    root = tmp_path / "smoke"
    shutil.copytree(FIXTURE, root)
    held = (root / PLAN).read_bytes()
    (root / PLAN).unlink()
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: the fixture")
    (root / PLAN).write_bytes(held)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: the fixture's own plan")
    return root
