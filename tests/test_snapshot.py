"""The guards on the snapshot helpers themselves: the ordinary walk, and the .git narrowing."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.gitfixture import git
from tests.snapshot import (
    assert_snapshot_changed,
    assert_snapshot_unchanged,
    describe_snapshot_diff,
    snapshot,
)

# Carried over with the tests: both build a real repository, and `tests/test_install_path.py`
# skipped its whole module without `git`.
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def test_the_ordinary_walk_holds_a_files_bytes_and_not_only_its_name(tmp_path: Path) -> None:
    # **Two claims this module made and held neither of.**
    #
    # The first is the ordinary tree: both tests below build `root.mkdir()` + `git init` and
    # nothing else, so `os.walk` contributes zero entries and their `assert before` was
    # satisfied entirely by `.git/config`, which `git init` always writes. Measured: the walk
    # deleted outright — `snapshot` returning `dict(stable_git_snapshot(root))` — left this
    # module 2 passed. The helper's own guard file held half of what the helper does.
    #
    # The second is content. `snapshot` records `path.read_bytes()` and its consumers read that
    # as "the tree is byte-for-byte as it was", but no consumer ever plants a change that keeps
    # a file's length. Measured: `read_bytes()` replaced by the file's SIZE left
    # `tests/test_snapshot.py`, `tests/test_install_path.py` and all of `tests/attach/` at 113
    # passed — a `detach` that rewrote a settings file in place would have been invisible to
    # every one of them.
    #
    # So: two ordinary files, one of them nested, asserted present by name; then a rewrite of
    # the same length, asserted to be seen AND to be named in the diff message, which is the
    # part that is about content rather than about paths.
    #
    # Mutations (declared): the ordinary walk contributes nothing; the walk records each file's
    # size instead of its bytes.
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("alpha\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("bravo\n", encoding="utf-8")
    before = snapshot(root)
    assert "a.txt" in before, sorted(before)
    assert str(Path("sub") / "b.txt") in before, sorted(before)

    (root / "sub" / "b.txt").write_text("BRAVO\n", encoding="utf-8")
    after = assert_snapshot_changed(root, before)
    assert after[str(Path("sub") / "b.txt")] == b"BRAVO\n"
    assert f"changed=['{Path('sub') / 'b.txt'}']" in describe_snapshot_diff(before, after)


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
    # What this floor actually holds, said plainly: an empty working tree contributes nothing
    # to `before`, so `assert before` here was `.git/config` and never the ordinary walk. That
    # walk has its own case above.
    assert ".git/config" in before, sorted(before)

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
    assert ".git/config" in before, sorted(before)

    objects = root / ".git" / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / "maintenance.lock").write_bytes(b"")
    (root / ".git" / "gc.log").write_text("warning: there are too many unreachable\n")
    (objects / "info").mkdir(parents=True, exist_ok=True)
    (objects / "info" / "commit-graph").write_bytes(b"CGPH")
    assert_snapshot_unchanged(root, before)
