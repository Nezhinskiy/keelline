from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.config.schema import Config
from keelline.memory.store import (
    inside_project,
    main_checkout,
    overlay_root,
    refusal_reason,
    resolve,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

CONFIG = """
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"

[memory]
mode = "{mode}"
groups = {groups}
index_extra = []
"""

REMOTE = "git@example.com:acme/widget.git"


def a_config(root: Path, mode: str, groups: str = '["developer", "project-stable"]') -> Config:
    (root / CONFIG_FILE).write_text(CONFIG.format(mode=mode, groups=groups), encoding="utf-8")
    return load(root, machine=root / "absent.toml")


def git(root: Path, *args: str) -> None:
    # The developer's own git configuration must not reach these runs: `commit.gpgsign`,
    # `core.hooksPath` and `init.templateDir` can each hang or fail a commit that has nothing
    # to do with the code under test.
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


def a_repo(root: Path, remote: str = REMOTE) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", remote)


def an_overlay(
    base: Path, *, projects: tuple[str, ...] = ("widget",), remote: str = REMOTE
) -> Path:
    overlay = base / "overlay"
    (overlay / "common" / "memory").mkdir(parents=True)
    (overlay / "common" / "memory" / "keep.md").write_text("x", encoding="utf-8")
    for name in projects:
        home = overlay / "projects" / name
        (home / "memory" / "project-stable").mkdir(parents=True)
        (home / PROJECT_FILE).write_text(
            f'remote = "{remote}"\nfirst_attach = "2026-09-12"\n', encoding="utf-8"
        )
    return overlay


PROJECT_FILE = "project.toml"


def a_machine_file(base: Path, overlay: Path | None) -> Path:
    path = base / "machine.toml"
    path.write_text("" if overlay is None else f'[overlay]\nroot = "{overlay}"\n', encoding="utf-8")
    return path


def a_tree(root: Path, overlay: Path, project: str = "widget") -> None:
    """The five-link tree §6.3 has `attach` create: `developer` into the overlay's common
    notes, the project-scoped groups into its own."""
    memory = root / "docs" / "memory"
    memory.mkdir(parents=True)
    (memory / "developer").symlink_to(overlay / "common" / "memory", target_is_directory=True)
    (memory / "project-stable").symlink_to(
        overlay / "projects" / project / "memory" / "project-stable", target_is_directory=True
    )


# --- the three modes ---------------------------------------------------------------------


def test_in_repo_mode_resolves_real_directories(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root)
    for group in ("developer", "project-stable"):
        (root / "docs" / "memory" / group).mkdir(parents=True)
    store = resolve(root, a_config(root, "in-repo"))
    assert store is not None
    assert store.path == root / "docs" / "memory"
    assert sorted(store.groups) == ["developer", "project-stable"]


def test_in_repo_mode_refuses_a_symlinked_store(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "developer").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs" / "memory").symlink_to(elsewhere, target_is_directory=True)
    config = a_config(root, "in-repo")
    assert resolve(root, config) is None
    assert "symlink" in (refusal_reason(root, config) or "")


def test_local_only_mode_uses_dot_keelline(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root)
    (root / ".keelline" / "local" / "memory" / "developer").mkdir(parents=True)
    store = resolve(root, a_config(root, "local-only"))
    assert store is not None
    assert store.path == root / ".keelline" / "local" / "memory"
    assert inside_project(store) is True


def test_local_only_mode_refuses_a_symlinked_store(tmp_path: Path) -> None:
    # A clone can ship `.keelline/local/memory` as a symlink exactly as easily as it can ship
    # `paths.memory` as one — the same real-directory guarantee `in-repo` and `overlay` get.
    root = tmp_path / "project"
    a_repo(root)
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "developer").mkdir(parents=True)
    (root / ".keelline" / "local").mkdir(parents=True)
    (root / ".keelline" / "local" / "memory").symlink_to(elsewhere, target_is_directory=True)
    config = a_config(root, "local-only")
    assert resolve(root, config) is None
    assert "symlink" in (refusal_reason(root, config) or "")


def test_overlay_mode_honours_the_tree_attach_creates(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root)
    overlay = an_overlay(tmp_path)
    a_tree(root, overlay)
    store = resolve(root, a_config(root, "overlay"), machine=a_machine_file(tmp_path, overlay))
    assert store is not None
    assert sorted(store.groups) == ["developer", "project-stable"]
    # The cross-project half is the point: a single link at paths.memory cannot reach it.
    assert store.groups["developer"].resolve() == (overlay / "common" / "memory").resolve()
    assert inside_project(store) is False


# --- the four ways the answer can be a lie --------------------------------------------------


def test_a_link_into_another_project_inside_the_same_overlay_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root)
    overlay = an_overlay(tmp_path, projects=("widget", "secret-client"))
    (overlay / "projects" / "secret-client" / "memory" / "project-stable" / "nda.md").write_text(
        "confidential\n", encoding="utf-8"
    )
    memory = root / "docs" / "memory"
    memory.mkdir(parents=True)
    (memory / "developer").symlink_to(overlay / "common" / "memory", target_is_directory=True)
    (memory / "project-stable").symlink_to(
        overlay / "projects" / "secret-client" / "memory" / "project-stable",
        target_is_directory=True,
    )
    config = a_config(root, "overlay")
    store = resolve(root, config, machine=a_machine_file(tmp_path, overlay))
    assert store is not None  # `developer` is legitimate and still resolves
    assert "project-stable" not in store.groups
    assert "sideways" not in str(store.unavailable)
    assert "outside this project's share" in store.unavailable["project-stable"]


def test_overlay_mode_refuses_a_symlinked_paths_memory_into_another_project(
    tmp_path: Path,
) -> None:
    # §9.1 check 1: in overlay mode `paths.memory` must itself be a real directory holding one
    # link per group. A group reached *through* a symlinked `paths.memory` is not itself a
    # symlink, so the per-group check (§9.1 check 3, `permitted_roots`) never sees it — the
    # shape check is what has to catch this, and it must fire regardless of mode.
    root = tmp_path / "project"
    a_repo(root)
    overlay = an_overlay(tmp_path, projects=("widget", "secret-client"))
    (overlay / "projects" / "secret-client" / "memory" / "project-stable" / "nda.md").write_text(
        "confidential\n", encoding="utf-8"
    )
    (root / "docs").mkdir()
    (root / "docs" / "memory").symlink_to(
        overlay / "projects" / "secret-client" / "memory", target_is_directory=True
    )
    config = a_config(root, "overlay")
    machine = a_machine_file(tmp_path, overlay)
    store = resolve(root, config, machine=machine)
    # A refused store carries no `groups` at all, which is the proof the victim's `nda.md` was
    # never reachable through it.
    assert store is None
    assert refusal_reason(root, config, machine=machine) is not None


def test_a_group_name_that_escapes_the_store_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root)
    # `"../../secret"` from the store (`root/docs/memory`) resolves to `root/secret`, two
    # levels up — not to `tmp_path/secret`, which is a level further still. The leak has to
    # exist at the location the group name actually resolves to, or a mutation that drops the
    # containment guard would be masked by the ordinary "not in the store" / `exists()` check
    # instead of exposing the escape.
    (root / "secret").mkdir()
    (root / "secret" / "leaked.md").write_text("outside the store\n", encoding="utf-8")
    (root / "docs" / "memory" / "developer").mkdir(parents=True)
    config = a_config(root, "in-repo", groups='["developer", "../../secret"]')
    store = resolve(root, config)
    assert store is not None
    assert list(store.groups) == ["developer"]
    assert "../../secret" in store.unavailable


def test_overlay_mode_refuses_when_the_remote_does_not_match(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root, remote="git@example.com:acme/other.git")
    overlay = an_overlay(tmp_path)
    a_tree(root, overlay)
    config = a_config(root, "overlay")
    machine = a_machine_file(tmp_path, overlay)
    assert resolve(root, config, machine=machine) is None
    assert "remote" in (refusal_reason(root, config, machine=machine) or "")


def test_overlay_mode_refuses_without_a_recorded_overlay_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root)
    overlay = an_overlay(tmp_path)
    a_tree(root, overlay)
    assert resolve(root, a_config(root, "overlay"), machine=a_machine_file(tmp_path, None)) is None


def test_an_environment_variable_never_selects_a_store(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root)
    (root / ".keelline" / "local" / "memory" / "developer").mkdir(parents=True)
    hostile = tmp_path / "hostile"
    hostile.mkdir()
    env = {"KEELLINE_STORE": str(hostile), "CLAUDE_MEMORY_DIR": str(hostile)}
    store = resolve(root, a_config(root, "local-only"), env=env)
    assert store is not None
    assert store.path == root / ".keelline" / "local" / "memory"


def test_an_inherited_git_dir_cannot_redirect_the_worktree_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    victim = tmp_path / "victim"
    a_repo(victim)
    (victim / "docs" / "memory" / "developer").mkdir(parents=True)
    hostile = tmp_path / "hostile"
    a_repo(hostile)
    monkeypatch.setenv("GIT_DIR", str(victim / ".git"))
    config = a_config(hostile, "in-repo")
    # Whatever git answers, the fallback only runs for a real ancestor of this root.
    assert resolve(hostile, config) is None


def test_a_worktree_resolves_through_the_main_checkout(tmp_path: Path) -> None:
    root = tmp_path / "project"
    a_repo(root)
    for group in ("developer", "project-stable"):
        (root / "docs" / "memory" / group).mkdir(parents=True)
    (root / "README.md").write_text("x", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    tree = root / "worktrees" / "side"
    git(root, "worktree", "add", "-q", str(tree), "-b", "side")
    assert main_checkout(tree).resolve() == root.resolve()
    store = resolve(tree, a_config(tree, "in-repo"))
    assert store is not None
    assert store.path.resolve() == (root / "docs" / "memory").resolve()


def test_overlay_root_reads_the_machine_file(tmp_path: Path) -> None:
    overlay = tmp_path / "o"
    overlay.mkdir()
    assert overlay_root(a_machine_file(tmp_path, overlay)) == overlay
    assert overlay_root(a_machine_file(tmp_path, None)) is None
    assert overlay_root(tmp_path / "absent.toml") is None
