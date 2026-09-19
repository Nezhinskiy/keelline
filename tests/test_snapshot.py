"""The two guards on the snapshot helpers' own narrowing, beside the helpers they hold."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.snapshot import (
    assert_snapshot_changed,
    assert_snapshot_unchanged,
    git,
    snapshot,
)

# Carried over with the tests: both build a real repository, and `tests/test_install_path.py`
# skipped its whole module without `git`.
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def test_the_narrowed_git_walk_still_catches_a_write_to_each_stable_path(tmp_path: Path) -> None:
    # The non-vacuity guard for the narrowing itself: `snapshot` no longer walks all of
    # `.git`, and a narrowing that stopped noticing a hook dropped into `.git/hooks/` or an
    # ignore region added to `.git/info/exclude` would be a regression wearing a fix's clothes.
    # Plant a file at each of the three stable spots the review named and require the snapshot
    # to see every one of them, one path at a time.
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    before = snapshot(root)
    assert before

    (root / ".git" / "info" / "exclude").write_text("/planted-by-a-defect\n", encoding="utf-8")
    after_exclude = assert_snapshot_changed(root, before)
    assert ".git/info/exclude" in after_exclude

    with (root / ".git" / "config").open("a", encoding="utf-8") as handle:
        handle.write('[planted]\n\tby = "a-defect"\n')
    after_config = assert_snapshot_changed(root, after_exclude)
    assert ".git/config" in after_config

    hooks = root / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    after_hook = assert_snapshot_changed(root, after_config)
    assert ".git/hooks/pre-commit" in after_hook


def test_the_narrowed_git_walk_ignores_gits_own_background_bookkeeping(tmp_path: Path) -> None:
    # The defect the review found: `checks (ubuntu-latest, 3.13)` failed because git's own
    # background maintenance dropped `objects/maintenance.lock` between two snapshots, and the
    # old, unrestricted walk over `.git` treated that as a write `attach`/`detach` had made.
    # Plant the same artifacts by hand — a lock file, a gc log, a commit-graph — and require
    # the narrowed walk to stay unaffected by all three.
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    before = snapshot(root)
    assert before

    objects = root / ".git" / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / "maintenance.lock").write_bytes(b"")
    (root / ".git" / "gc.log").write_text("warning: there are too many unreachable\n")
    (objects / "info").mkdir(parents=True, exist_ok=True)
    (objects / "info" / "commit-graph").write_bytes(b"CGPH")
    assert_snapshot_unchanged(root, before)
