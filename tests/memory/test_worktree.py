from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.config.schema import Config
from keelline.memory.store import Store, resolve
from keelline.memory.worktree import harness_memory_path, link, linked_names

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


def git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


def a_checkout(
    tmp_path: Path, *, groups: tuple[str, ...] = ("developer", "project-stable")
) -> tuple[Path, Store, Config]:
    root = tmp_path / "project"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@example.com:acme/widget.git")
    base = root / "docs" / "memory"
    for group in groups:
        (base / group).mkdir(parents=True)
    (base / "MEMORY.md").write_text("# Memory Index\n", encoding="utf-8")
    listed = "[" + ", ".join(f'"{g}"' for g in groups) + "]"
    (root / CONFIG_FILE).write_text(CONFIG.format(mode="in-repo", groups=listed), encoding="utf-8")
    config = load(root, machine=tmp_path / "absent.toml")
    store = resolve(root, config)
    assert store is not None
    (root / "README.md").write_text("x", encoding="utf-8")
    # The store is git-ignored, which is the whole reason a worktree has none of it.
    (root / ".gitignore").write_text("docs/memory/\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    return root, store, config


def a_worktree(root: Path, where: Path) -> Path:
    git(root, "worktree", "add", "-q", str(where), "-b", "side")
    return where


def test_the_main_checkout_gets_no_links(tmp_path: Path) -> None:
    root, store, config = a_checkout(tmp_path)
    assert link(root, store, config, home=tmp_path / "home") == []


def test_a_worktree_gets_one_link_per_group_plus_the_index(tmp_path: Path) -> None:
    root, store, config = a_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    created = {p.name for p in link(tree, store, config, home=tmp_path / "home")}
    assert {"MEMORY.md", "developer", "project-stable"} <= created
    assert (tree / "docs" / "memory" / "developer").is_symlink()


def test_the_group_list_comes_from_the_configuration(tmp_path: Path) -> None:
    root, store, config = a_checkout(tmp_path, groups=("developer", "specs"))
    assert "specs" in linked_names(config)
    tree = a_worktree(root, tmp_path / "wt")
    created = {p.name for p in link(tree, store, config, home=tmp_path / "home")}
    assert "specs" in created


def test_the_links_resolve_to_the_real_store_not_to_another_symlink(tmp_path: Path) -> None:
    root, store, config = a_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    link(tree, store, config, home=tmp_path / "home")
    target = (tree / "docs" / "memory" / "developer").readlink()
    assert not target.is_symlink()
    assert target == (store.groups["developer"]).resolve()


def test_linking_twice_creates_nothing_the_second_time(tmp_path: Path) -> None:
    root, store, config = a_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    link(tree, store, config, home=tmp_path / "home")
    assert link(tree, store, config, home=tmp_path / "home") == []


def test_a_real_directory_at_a_target_is_left_alone(tmp_path: Path) -> None:
    root, store, config = a_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    mine = tree / "docs" / "memory" / "developer"
    mine.mkdir(parents=True)
    (mine / "mine.md").write_text("keep\n", encoding="utf-8")
    link(tree, store, config, home=tmp_path / "home")
    assert (mine / "mine.md").read_text(encoding="utf-8") == "keep\n"
    assert not mine.is_symlink()


def test_a_dangling_symlink_is_replaced(tmp_path: Path) -> None:
    root, store, config = a_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    base = tree / "docs" / "memory"
    base.mkdir(parents=True, exist_ok=True)
    (base / "developer").symlink_to(tmp_path / "gone")
    link(tree, store, config, home=tmp_path / "home")
    assert (base / "developer").resolve() == store.groups["developer"].resolve()


def test_a_symlink_to_the_wrong_target_is_replaced(tmp_path: Path) -> None:
    # Distinct from the dangling case above: this symlink resolves fine, just to the wrong
    # place, so a guard written as a bare `Path.exists()` (true for a valid symlink) would
    # leave it standing. Only comparing `readlink()` against the intended source catches this.
    root, store, config = a_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    base = tree / "docs" / "memory"
    base.mkdir(parents=True, exist_ok=True)
    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (base / "developer").symlink_to(wrong, target_is_directory=True)
    link(tree, store, config, home=tmp_path / "home")
    assert (base / "developer").resolve() == store.groups["developer"].resolve()


def test_the_harness_memory_directory_is_keyed_by_the_worktree_path(tmp_path: Path) -> None:
    root, store, config = a_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    home = tmp_path / "home"
    link(tree, store, config, home=home)
    assert harness_memory_path(tree, home).is_symlink()
    slug = str(tree.resolve()).replace("/", "-").replace(".", "-")
    assert (home / ".claude" / "projects" / slug / "memory").is_symlink()


def test_nothing_outside_the_worktree_and_the_home_directory_is_touched(tmp_path: Path) -> None:
    root, store, config = a_checkout(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    tree = a_worktree(root, tmp_path / "wt")
    link(tree, store, config, home=tmp_path / "home")
    assert list(elsewhere.iterdir()) == []


def test_no_new_top_level_entry_appears_anywhere_but_the_home_directory(tmp_path: Path) -> None:
    # The decoy-directory check above only notices a write that lands *inside* `elsewhere`;
    # a stray write to a different sibling of the worktree (say `tmp_path / "docs"`) would
    # leave `elsewhere` untouched and pass unnoticed. This snapshots every entry `tmp_path`
    # holds right before `link()` runs and requires the only new one afterwards to be `home`
    # itself — home is expected to spring into existence, everything else is not.
    root, store, config = a_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    home = tmp_path / "home"
    before = set(tmp_path.iterdir())
    link(tree, store, config, home=home)
    after = set(tmp_path.iterdir())
    assert after - before <= {home}


# --- an overlay fixture, to discriminate a mutation the in-repo tests above cannot ------------
#
# `store.groups[group]` and `store.path / group` are the same expression for every group that
# resolved cleanly, so no in-repo fixture can tell `link()` apart from a version that sourced
# from `store.path / group` directly. They diverge only for a group `resolve()` *refused* and
# therefore left out of `store.groups` — the store's own overlay-boundary check (§9.1 check 3).
# A worktree link built from `store.path / group` would still find a real symlink sitting at
# that path in the checkout and materialise it, carrying a sideways link across the project
# boundary into every worktree. This is the "resolve test again, under an overlay fixture" the
# brief's mutation notes ask for, since the nine tests above never produce an unavailable group.


def an_overlay_checkout(tmp_path: Path) -> tuple[Path, Store, Config]:
    root = tmp_path / "project"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@example.com:acme/widget.git")
    overlay = tmp_path / "overlay"
    (overlay / "common" / "memory").mkdir(parents=True)
    (overlay / "projects" / "widget" / "project.toml").parent.mkdir(parents=True)
    (overlay / "projects" / "widget" / "project.toml").write_text(
        'remote = "git@example.com:acme/widget.git"\n', encoding="utf-8"
    )
    # `other`'s share of the overlay never belongs to `widget` and carries no binding record of
    # its own; the point is that a symlink can still be *made* to point there.
    other = overlay / "projects" / "other" / "memory" / "project-stable"
    other.mkdir(parents=True)
    (other / "nda.md").write_text("confidential\n", encoding="utf-8")
    memory = root / "docs" / "memory"
    memory.mkdir(parents=True)
    (memory / "developer").symlink_to(overlay / "common" / "memory", target_is_directory=True)
    (memory / "project-stable").symlink_to(other, target_is_directory=True)
    (memory / "MEMORY.md").write_text("# Memory Index\n", encoding="utf-8")
    (root / CONFIG_FILE).write_text(
        CONFIG.format(mode="overlay", groups='["developer", "project-stable"]'),
        encoding="utf-8",
    )
    machine = tmp_path / "machine.toml"
    machine.write_text(f'[overlay]\nroot = "{overlay}"\n', encoding="utf-8")
    config = load(root, machine=machine)
    store = resolve(root, config, machine=machine)
    assert store is not None
    (root / "README.md").write_text("x", encoding="utf-8")
    (root / ".gitignore").write_text("docs/memory/\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    return root, store, config


def test_a_group_the_overlay_boundary_refused_is_never_linked_into_a_worktree(
    tmp_path: Path,
) -> None:
    root, store, config = an_overlay_checkout(tmp_path)
    # Sanity: the store itself already refused the sideways group (§9.1 check 3) — the test
    # below is only meaningful because `link()` receives a `store` that already excludes it.
    assert "project-stable" not in store.groups
    tree = a_worktree(root, tmp_path / "wt")
    created = link(tree, store, config, home=tmp_path / "home")
    assert "project-stable" not in {p.name for p in created}
    assert not (tree / "docs" / "memory" / "project-stable").exists()
    assert (tree / "docs" / "memory" / "developer").is_symlink()


def test_an_overlay_groups_worktree_link_skips_the_main_checkouts_own_hop(
    tmp_path: Path,
) -> None:
    # `test_the_links_resolve_to_the_real_store_not_to_another_symlink` above uses an in-repo
    # fixture, where `store.groups["developer"]` already *is* a real directory — resolving it
    # or not makes no difference, so that test cannot tell a chained link from a direct one.
    # Only an overlay fixture puts a symlink at `store.groups["developer"]` itself (the main
    # checkout's own link into `common/memory`), which is the one case the module's docstring
    # is about: a worktree link sourced from that unresolved value would point at the main
    # checkout's link rather than at the store, and break the moment `detach` removes it.
    root, store, config = an_overlay_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    link(tree, store, config, home=tmp_path / "home")
    target = (tree / "docs" / "memory" / "developer").readlink()
    assert store.groups["developer"].is_symlink()  # the hop this link must skip
    assert target != store.groups["developer"]
    assert target == store.groups["developer"].resolve()
