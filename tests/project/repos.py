"""The initialised repository `upgrade`'s and `uninstall`'s tests start from, and how they read it.

One module rather than a copy per test file: both commands are read against the same `init`, and
two copies of the fixture would drift the way the suite's twenty-three `git` helpers once did
(`tests/gitfixture.py` says how).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from keelline.project.init import init
from keelline.runner import Runner
from tests.gitfixture import LsRemote, git

BEFORE = "# ours, from before Keelline\n"


def initialised(
    tmp_path: Path,
    *,
    runner: Runner | None = None,
    ci: bool = False,
    document: str = "",
    files: Mapping[str, str] | None = None,
) -> Path:
    """`init --yes` over a repository that already held a README, `document` as its
    `keelline.toml` when one is given, and each of `files` (a root-relative path and its text)
    written before `init` runs."""
    root = tmp_path / "widget"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@github.com:owner/widget.git")
    (root / "README.md").write_text(BEFORE, encoding="utf-8")
    if document:
        (root / "keelline.toml").write_text(document, encoding="utf-8")
    for relative, text in (files or {}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    init(
        root,
        machine=tmp_path / "absent.toml",
        runner=runner or LsRemote(),
        yes=True,
        dry_run=False,
        ci=ci,
    )
    return root


def tree(root: Path) -> set[str]:
    """Every path under `root` but git's own, directories included, so one a run emptied and
    left behind is seen."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if ".git" not in p.parts}
