"""`attach` links the store into the owning checkout and into every worktree that already exists.

The main checkout is `worktree.attach_main`'s (the case `link` excludes); every other checkout
is `worktree.link`'s, unchanged. This module asserts that `attach` reaches both.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from keelline.attach.api import Attached, attach
from keelline.config.loader import load
from keelline.config.schema import Config
from keelline.memory.api import PartialLink, harness_memory_path
from tests.attach.test_binding import CONFIG, _machine
from tests.attach.test_write import FakeRunner

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


def _config(root: Path, machine: Path) -> Config:
    return load(root, machine=machine)


def _bound(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A committed repository in overlay mode, and the overlay that already records it."""
    root = tmp_path / "project"
    root.mkdir(parents=True)
    overlay = tmp_path / "overlay"
    (overlay / "common" / "memory").mkdir(parents=True)
    (overlay / "common" / "memory" / "shared.md").write_text("x", encoding="utf-8")
    own = overlay / "projects" / "p" / "memory"
    own.mkdir(parents=True)
    (own.parent / "project.toml").write_text(
        'remote = "git@example.com:o/p.git"\n', encoding="utf-8"
    )
    (overlay / "common" / "claude").mkdir(parents=True)
    (overlay / "common" / "codex").mkdir(parents=True)
    (root / "keelline.toml").write_text(CONFIG.format(name="p"), encoding="utf-8")
    (root / ".gitignore").write_text("docs/memory/\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "remote", "add", "origin", "git@example.com:o/p.git")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    return root, own, _machine(tmp_path, overlay=overlay)


def _attach(root: Path, store: Path, machine: Path, home: Path) -> Attached:
    return attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=FakeRunner(),
        home=home,
    )


def test_every_existing_worktree_is_linked(tmp_path: Path) -> None:
    # §6.3: "links memory into every existing worktree". A worktree created before the attach
    # is the common case — this repository has four of them. The main checkout is skipped here
    # because `attach_main` has already handled it, and `link` is a no-op there anyway.
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    _attach(root, store, machine, tmp_path / "home")
    assert (root / "docs" / "memory" / "developer").is_symlink()
    assert (side / "docs" / "memory" / "developer").is_symlink()
    assert (side / "docs" / "memory" / "project-stable").is_symlink()


def test_a_partial_link_failure_reports_what_it_made(tmp_path: Path) -> None:
    # `PartialLink` carries `.created` precisely so a half-built tree is repairable rather than
    # mysterious. attach must surface it, not swallow it into a generic failure.
    root, store, machine = _bound(tmp_path)
    side = tmp_path / "side"
    _git(root, "worktree", "add", "-q", str(side), "-b", "side")
    real = Path.symlink_to

    def refuse_inside_the_worktree(
        self: Path, target: Path, target_is_directory: bool = False
    ) -> None:
        if str(self).startswith(str(side)):
            raise OSError("this filesystem refuses symlinks")
        real(self, target, target_is_directory=target_is_directory)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "symlink_to", refuse_inside_the_worktree)
        with pytest.raises(PartialLink) as failed:
            _attach(root, store, machine, tmp_path / "home")
    assert failed.value.created == []
    assert (root / "docs" / "memory" / "developer").is_symlink()


def test_the_harness_fallback_is_recorded_so_it_can_be_withdrawn(tmp_path: Path) -> None:
    # §6.3 gives `~/.claude/projects/<slug>/memory` a fallback — `autoMemoryDirectory` in
    # settings.local.json — "because a settings-file value is subject to workspace trust and a
    # link is not". The symlink is preferred and the fallback is taken only when the link
    # cannot be made; when it is, it goes into the same ledger as everything else, because a
    # fallback nothing records is a setting that outlives its reason.
    import json

    from keelline.attach.api import ledger
    from keelline.memory.api import resolve
    from keelline.memory.trust import record

    root, store, machine = _bound(tmp_path)
    home = tmp_path / "home"
    _attach(root, store, machine, home)
    resolved = resolve(root, _config(root, machine), machine=machine)
    assert resolved is not None
    record(resolved, _config(root, machine))
    # A real directory where the link belongs: the case `_link` refuses to clobber, and the one
    # §6.3 names alongside a filesystem that has no symlinks.
    harness = harness_memory_path(root, home)
    harness.mkdir(parents=True)
    attached = _attach(root, store, machine, home)
    settings = json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    assert settings["autoMemoryDirectory"] == str(resolved.path.resolve())
    assert ledger(root).settings_keys == ("autoMemoryDirectory",)
    assert any("autoMemoryDirectory" in note for note in attached.notes)
