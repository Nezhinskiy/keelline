from __future__ import annotations

from pathlib import Path

from keelline.overlay.api import Sync, overlay_sync
from tests.gitfixture import git, needs_git


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "overlay"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# overlay\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: first")
    return root


@needs_git
def test_a_clean_repository_with_no_upstream_reports_no_upstream(tmp_path: Path) -> None:
    assert overlay_sync(_repo(tmp_path)) == Sync(dirty=0, ahead=None, asked=True)


@needs_git
def test_an_untracked_file_counts_as_uncommitted(tmp_path: Path) -> None:
    # A note the owner wrote and never added is exactly the change the other machine will
    # not see. Mutation (comment): `--untracked-files=no` -> this reddens.
    root = _repo(tmp_path)
    (root / "note.md").write_text("x\n", encoding="utf-8")
    assert overlay_sync(root).dirty == 1


@needs_git
def test_commits_ahead_of_the_upstream_are_counted(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-q", "-u", "origin", "main")
    assert overlay_sync(root).ahead == 0
    (root / "README.md").write_text("# overlay\n\nmore\n", encoding="utf-8")
    git(root, "commit", "-qam", "docs: more")
    assert overlay_sync(root) == Sync(dirty=0, ahead=1, asked=True)


def test_a_directory_git_cannot_answer_for_is_not_asked(tmp_path: Path) -> None:
    assert overlay_sync(tmp_path / "nowhere").asked is False
