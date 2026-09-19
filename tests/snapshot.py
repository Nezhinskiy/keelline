"""The tree-snapshot helpers three test modules share.

Here rather than in `tests/test_install_path.py`, because two `attach` test modules importing
an installer-focused module's private names was S3 of the install-path review.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


# The only `.git` paths a defect this guard cares about could actually land in: a hook dropped
# into `.git/hooks/`, a rule written to `.git/config`, an ignore region added to
# `.git/info/exclude`. Everything else under `.git` — `objects/`, `logs/`, `refs/`, a fresh
# `commit-graph`, a pack, `gc.log`, `objects/maintenance.lock` — is git's own background
# bookkeeping. The fixtures that build these repositories pin `GIT_CONFIG_GLOBAL` and
# `GIT_CONFIG_SYSTEM` to `os.devnull`, which leaves `gc.auto` and `maintenance.auto` at their
# defaults, so that bookkeeping can run — and does — between two snapshots taken moments apart.
_STABLE_GIT_FILES = (Path("config"), Path("info") / "exclude")


def stable_git_snapshot(root: Path) -> dict[str, bytes]:
    """The narrow slice of `.git` this guard reads: the two named files, plus every file
    under `hooks/`, by path relative to `root`."""
    git = root / ".git"
    files: dict[str, bytes] = {}
    for relative in _STABLE_GIT_FILES:
        candidate = git / relative
        if candidate.is_file():
            files[str(Path(".git") / relative)] = candidate.read_bytes()
    hooks = git / "hooks"
    if hooks.is_dir():
        for path in sorted(hooks.iterdir()):
            if path.is_file():
                files[str(Path(".git") / "hooks" / path.name)] = path.read_bytes()
    return files


def snapshot(root: Path) -> dict[str, bytes]:
    """Every regular file under the root, by relative path.

    `.git` is included deliberately — this is the walk that would catch an ignore region
    written to `.git/info/exclude` or a hook dropped into `.git/hooks` — but narrowed to the
    paths a defect could actually land in. See `stable_git_snapshot` for why the rest of
    `.git` is pruned rather than walked: it is a moving target, not a place this guard watches.
    """
    files: dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        if current == root:
            dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in filenames:
            path = current / name
            if path.is_file():
                files[str(path.relative_to(root))] = path.read_bytes()
    files.update(stable_git_snapshot(root))
    return files


def describe_snapshot_diff(before: dict[str, bytes], after: dict[str, bytes]) -> str:
    """A failure message a person can read: which paths came, went or changed, not a dump of
    every file's bytes — which is what the bare `dict == dict` assertion this backs used to
    print, `.git` object tree included, on the one CI job the race actually hit.
    """
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(path for path in before.keys() & after.keys() if before[path] != after[path])
    return f"snapshot differs: added={added} removed={removed} changed={changed}"


def assert_snapshot_unchanged(root: Path, before: dict[str, bytes]) -> None:
    after = snapshot(root)
    assert after == before, describe_snapshot_diff(before, after)


def assert_snapshot_changed(root: Path, before: dict[str, bytes]) -> dict[str, bytes]:
    after = snapshot(root)
    assert after != before, "expected at least one file under the root to differ; none did"
    return after
