from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.config.paths import PathEscape
from keelline.config.schema import Config
from keelline.memory.store import LOCAL_STORE, Store, resolve
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


def git(root: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    done = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, env=env
    )
    return done.stdout


def _a_repo(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@example.com:acme/widget.git")
    return root


def _commit_checkout(root: Path, *, ignore: str = "docs/memory/") -> None:
    (root / "README.md").write_text("x", encoding="utf-8")
    # The store is git-ignored, which is the whole reason a worktree has none of it. Which
    # directory that is depends on the mode: `local-only` keeps it at `.keelline/local/`, and
    # the ignore entry a mode ships is the one that covers the tree `link()` builds.
    (root / ".gitignore").write_text(f"{ignore}\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")


def a_checkout(
    tmp_path: Path, *, groups: tuple[str, ...] = ("developer", "project-stable")
) -> tuple[Path, Store, Config]:
    root = _a_repo(tmp_path)
    base = root / "docs" / "memory"
    for group in groups:
        (base / group).mkdir(parents=True)
    (base / "MEMORY.md").write_text("# Memory Index\n", encoding="utf-8")
    listed = "[" + ", ".join(f'"{g}"' for g in groups) + "]"
    (root / CONFIG_FILE).write_text(CONFIG.format(mode="in-repo", groups=listed), encoding="utf-8")
    config = load(root, machine=tmp_path / "absent.toml")
    store = resolve(root, config)
    assert store is not None
    _commit_checkout(root)
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
    root = _a_repo(tmp_path)
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
    _commit_checkout(root)
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


# --- the index gets no less scrutiny than a group ---------------------------------------------
#
# Every configured *group* reaches `link()` only after `store.py`'s own `_group_targets` has
# applied §9.1's per-link target rule (in overlay mode: honoured only inside this project's
# share, `permitted_roots`). `MEMORY.md` does not go through that gate at all — `store.py`
# tracks it as nothing (it is not a `memory.groups` entry), so `link()` has always read it
# straight off `store.path / INDEX_NAME` with no check on where it points. §6.3 does make a
# symlinked `MEMORY.md` legitimate in overlay mode, so the fix cannot be "refuse a symlinked
# index" — it has to be the same target rule a group gets, applied here too.


def an_overlay_checkout_with_a_leaked_index(tmp_path: Path) -> tuple[Path, Store, Config, Path]:
    """An overlay checkout whose own `MEMORY.md` is a symlink into a *different* project's
    share of the overlay — the boundary §9.1 draws for a group, drawn here for the index."""
    root = _a_repo(tmp_path)
    overlay = tmp_path / "overlay"
    (overlay / "common" / "memory").mkdir(parents=True)
    (overlay / "projects" / "widget" / "project.toml").parent.mkdir(parents=True)
    (overlay / "projects" / "widget" / "project.toml").write_text(
        'remote = "git@example.com:acme/widget.git"\n', encoding="utf-8"
    )
    other_index = overlay / "projects" / "other" / "memory" / "MEMORY.md"
    other_index.parent.mkdir(parents=True)
    other_index.write_text("# confidential index\n", encoding="utf-8")
    memory = root / "docs" / "memory"
    memory.mkdir(parents=True)
    (memory / "developer").symlink_to(overlay / "common" / "memory", target_is_directory=True)
    (memory / "MEMORY.md").symlink_to(other_index)
    (root / CONFIG_FILE).write_text(
        CONFIG.format(mode="overlay", groups='["developer"]'), encoding="utf-8"
    )
    machine = tmp_path / "machine.toml"
    machine.write_text(f'[overlay]\nroot = "{overlay}"\n', encoding="utf-8")
    config = load(root, machine=machine)
    store = resolve(root, config, machine=machine)
    assert store is not None
    _commit_checkout(root)
    return root, store, config, machine


def test_an_index_the_overlay_boundary_refuses_is_never_linked_into_a_worktree(
    tmp_path: Path,
) -> None:
    root, store, config, machine = an_overlay_checkout_with_a_leaked_index(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    created = link(tree, store, config, home=tmp_path / "home", machine=machine)
    assert "MEMORY.md" not in {p.name for p in created}
    assert not (tree / "docs" / "memory" / "MEMORY.md").exists()


def an_overlay_checkout_with_a_linked_index(tmp_path: Path) -> tuple[Path, Store, Config, Path]:
    """§6.3's legitimate case: `MEMORY.md` symlinked into *this* project's own share of the
    overlay. The boundary check must let this through — it is not "refuse every symlinked
    index", it is "refuse one outside this project's share"."""
    root = _a_repo(tmp_path)
    overlay = tmp_path / "overlay"
    (overlay / "common" / "memory").mkdir(parents=True)
    project_share = overlay / "projects" / "widget" / "memory"
    project_share.mkdir(parents=True)
    (project_share / "MEMORY.md").write_text("# Memory Index\n", encoding="utf-8")
    (overlay / "projects" / "widget" / "project.toml").write_text(
        'remote = "git@example.com:acme/widget.git"\n', encoding="utf-8"
    )
    memory = root / "docs" / "memory"
    memory.mkdir(parents=True)
    (memory / "developer").symlink_to(overlay / "common" / "memory", target_is_directory=True)
    (memory / "MEMORY.md").symlink_to(project_share / "MEMORY.md")
    (root / CONFIG_FILE).write_text(
        CONFIG.format(mode="overlay", groups='["developer"]'), encoding="utf-8"
    )
    machine = tmp_path / "machine.toml"
    machine.write_text(f'[overlay]\nroot = "{overlay}"\n', encoding="utf-8")
    config = load(root, machine=machine)
    store = resolve(root, config, machine=machine)
    assert store is not None
    _commit_checkout(root)
    return root, store, config, machine


def test_an_index_inside_the_overlay_boundary_is_still_linked(tmp_path: Path) -> None:
    # The index is a *file* nested inside the permitted share directory, never equal to the
    # share directory itself — so a boundary check written as bare equality (`resolved == root`)
    # would refuse every legitimate overlay-mode index outright. Only a proper containment
    # check (`is_relative_to`) can tell "inside this project's share" from "is this project's
    # share".
    root, store, config, machine = an_overlay_checkout_with_a_linked_index(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    created = link(tree, store, config, home=tmp_path / "home", machine=machine)
    assert "MEMORY.md" in {p.name for p in created}
    linked = (tree / "docs" / "memory" / "MEMORY.md").resolve()
    expected = tmp_path / "overlay" / "projects" / "widget" / "memory" / "MEMORY.md"
    assert linked == expected.resolve()


def test_a_symlinked_index_is_refused_outside_overlay_mode_even_with_an_overlay_configured(
    tmp_path: Path,
) -> None:
    # Mirrors `_group_targets`: a symlinked group in in-repo mode is refused unconditionally,
    # never opportunistically checked against a machine-level overlay that happens to be
    # configured (possibly for other projects entirely) — `mode` governs strictly. The index
    # must be held to the identical rule, or it would trust an overlay this project's own
    # configuration never opted into.
    root = _a_repo(tmp_path)
    overlay = tmp_path / "overlay"
    project_share = overlay / "projects" / "widget" / "memory"
    project_share.mkdir(parents=True)
    (project_share / "MEMORY.md").write_text("# Memory Index\n", encoding="utf-8")
    memory = root / "docs" / "memory"
    (memory / "developer").mkdir(parents=True)
    (memory / "MEMORY.md").symlink_to(project_share / "MEMORY.md")
    (root / CONFIG_FILE).write_text(
        CONFIG.format(mode="in-repo", groups='["developer"]'), encoding="utf-8"
    )
    machine = tmp_path / "machine.toml"
    machine.write_text(f'[overlay]\nroot = "{overlay}"\n', encoding="utf-8")
    config = load(root, machine=machine)
    store = resolve(root, config, machine=machine)
    assert store is not None
    _commit_checkout(root)
    tree = a_worktree(root, tmp_path / "wt")
    created = link(tree, store, config, home=tmp_path / "home", machine=machine)
    assert "MEMORY.md" not in {p.name for p in created}
    assert not (tree / "docs" / "memory" / "MEMORY.md").exists()


# --- `local-only`, the preset default, which no test above reaches --------------------------
#
# Every fixture above declares `in-repo` or `overlay`, where `paths.memory` *is* the store —
# so `worktree / config.paths.memory` and the store's own place in the checkout are the same
# directory and no test could tell them apart. `local-only` separates them: the resolver uses
# `.keelline/local/memory` and never consults `paths.memory`, while `link()` used to build the
# tree at `paths.memory` unconditionally. That is one bug wearing two faces — the links landing
# where the resolver never looks and outside the `.gitignore` entry the mode relies on, and a
# repository-controlled `paths.memory` choosing a directory anywhere on the filesystem.

LOCAL_ONLY_CONFIG = """
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

[paths]
memory = "{paths_memory}"

[memory]
mode = "local-only"
groups = ["developer"]
index_extra = []
"""

NOTE = '---\nname: a\ndescription: d\nindex: "t → a"\n---\n\nBody.\n'


def a_local_only_checkout(
    tmp_path: Path, *, paths_memory: str = "docs/memory", leaks_to: Path | None = None
) -> tuple[Path, Store, Config]:
    """A `local-only` checkout, optionally with `paths.memory` committed as a symlink out of it.

    `config/paths.py` passes `allow_final_symlink=True` for `memory` and `contained()` does not
    resolve the final component, so that symlink loads without complaint — which is the whole
    reason `link()` must not derive anything from the value.
    """
    root = _a_repo(tmp_path)
    base = root / LOCAL_STORE
    (base / "developer").mkdir(parents=True)
    (base / "developer" / "a.md").write_text(NOTE, encoding="utf-8")
    (base / "MEMORY.md").write_text("# Memory Index\n", encoding="utf-8")
    if leaks_to is not None:
        # Relative, so it resolves to the same place from the checkout and from any worktree
        # beside it — which is what makes this reachable from a session in `../side`.
        sideways = os.path.relpath(leaks_to, root)
        (root / paths_memory).symlink_to(sideways, target_is_directory=True)
    (root / CONFIG_FILE).write_text(
        LOCAL_ONLY_CONFIG.format(paths_memory=paths_memory), encoding="utf-8"
    )
    config = load(root, machine=tmp_path / "absent.toml")
    store = resolve(root, config)
    assert store is not None
    _commit_checkout(root, ignore=".keelline/local/")
    return root, store, config


def test_a_local_only_worktree_is_linked_where_local_only_keeps_the_store(
    tmp_path: Path,
) -> None:
    # The functional half of the same defect: in `local-only` the resolver reads
    # `.keelline/local/memory` and `paths.memory` is never consulted, so a tree built at
    # `paths.memory` put every link where nothing would ever read it — and, because the mode's
    # `.gitignore` entry covers `.keelline/local/` and not `docs/`, left the worktree dirty.
    root, store, config = a_local_only_checkout(tmp_path)
    tree = a_worktree(root, tmp_path / "wt")
    created = link(tree, store, config, home=tmp_path / "home")
    linked = tree / LOCAL_STORE / "developer"
    assert linked in created
    assert linked.resolve() == store.groups["developer"].resolve()
    assert not (tree / config.paths.memory).exists()
    assert git(tree, "status", "--porcelain") == ""


def test_a_symlinked_paths_memory_is_never_where_the_worktree_tree_is_built(
    tmp_path: Path,
) -> None:
    # The hostile counterpart of the two isolation tests above, which hold only because their
    # `paths.memory` is benign. `paths.memory` is repository-controlled, a committed symlink
    # there loads without complaint, and `base.mkdir(parents=True, exist_ok=True)` followed it
    # — so a `SessionStart` in a worktree planted symlinks to repository-authored notes in the
    # victim's `~/.claude`, where names like `CLAUDE.md` or `commands/` are normally absent.
    victim = tmp_path / "fakehome" / ".claude"
    victim.mkdir(parents=True)
    root, store, config = a_local_only_checkout(tmp_path, paths_memory="mem", leaks_to=victim)
    tree = a_worktree(root, tmp_path / "wt")
    # The traversal really is reachable from the worktree: this is the path `link()` was given.
    assert (tree / "mem").resolve() == victim.resolve()
    home = tmp_path / "home"
    before = set(tmp_path.iterdir())
    link(tree, store, config, home=home)
    assert list(victim.iterdir()) == []
    assert set(tmp_path.iterdir()) - before <= {home}
    assert (tree / LOCAL_STORE / "developer").is_symlink()


def test_a_group_target_that_escapes_the_worktree_tree_is_refused_rather_than_skipped(
    tmp_path: Path,
) -> None:
    # `store.groups` was validated against the *main checkout's* tree. A worktree is a separate
    # checkout of a separate branch, so its own copy of that subtree can hold a symlink the main
    # one does not, and `_link`'s `mkdir(parents=True)` follows it. Every target is therefore
    # re-derived against the tree it is about to be created in — and an escape is a refusal,
    # because skipping one name leaves the next name in the list to try the same thing.
    root, store, config = a_checkout(tmp_path, groups=("sub/developer",))
    tree = a_worktree(root, tmp_path / "wt")
    outside = tmp_path / "outside"
    outside.mkdir()
    base = tree / "docs" / "memory"
    base.mkdir(parents=True, exist_ok=True)
    (base / "sub").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathEscape):
        link(tree, store, config, home=tmp_path / "home")
    assert list(outside.iterdir()) == []
