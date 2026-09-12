"""Make the store reachable from a git worktree.

A worktree is a separate checkout, and the store is git-ignored, so a session working in one
sees none of it — and the harness keys its own project-memory directory by working directory,
so that is missing too. Both gaps are closed with symlinks, never copies: a copy answers reads
and breaks writes, because a note created from a worktree would live only there, diverge from
the canonical store, and vanish with the worktree.

Three rules the shell version of this paid for:

- **A real file or directory at a target is never clobbered.** It is either unmerged work or a
  store the harness created on its own, and destroying either silently is worse than the gap.
- **A dangling symlink is replaced.** `Path.exists()` reports it as absent while `symlink_to`
  still refuses, which aborted the whole hook.
- **The list of what to link is derived, never hand-maintained.** The shell version carried an
  allowlist, and a group added to the store and not to that line was absent from the tree, and
  therefore absent from the floor the reference guard derived from the tree — invisible twice.

Links point at the *resolved* group target, not at the main checkout's own link: in overlay
mode that link is itself a symlink, and a chain breaks the moment `detach` removes the first
hop. It also matters for a group the store's own §9.1 checks refused: such a group never makes
it into `store.groups`, so sourcing from that dict (and never from `store.path / name`) is what
keeps a boundary the store already enforced from being bypassed a second time here.

The index gets no exemption from that boundary. `store.py` does not track `MEMORY.md` as a
group — it is not a `memory.groups` entry — so nothing upstream ever applies §9.1's per-link
target rule to it the way `_group_targets` applies it to every configured group. §6.3 makes a
symlinked index a legitimate member of the tree `attach` creates, so the fix cannot be "refuse a
symlinked index"; it has to be the identical rule a group gets: in overlay mode, honoured only
inside this project's own share of the recorded overlay (`permitted_roots`), and outside overlay
mode refused outright, exactly as an ungoverned group symlink would be.
"""

from __future__ import annotations

from pathlib import Path

from keelline.config.schema import Config
from keelline.memory.index import INDEX_NAME
from keelline.memory.store import Store, main_checkout, overlay_root, permitted_roots


def linked_names(config: Config) -> tuple[str, ...]:
    """Every name a worktree's link tree should hold: the index, then each configured group."""
    return (INDEX_NAME, *config.memory.groups)


def harness_memory_path(worktree: Path, home: Path | None = None) -> Path:
    """`~/.claude/projects/<slug>/memory`; the slug is the path with `/` and `.` as `-`."""
    base = Path.home() if home is None else home
    slug = str(worktree.resolve()).replace("/", "-").replace(".", "-")
    return base / ".claude" / "projects" / slug / "memory"


def _link(source: Path, target: Path) -> bool:
    """Create or repair a symlink; report whether it did anything.

    A real file or directory at `target` is left alone (`exists()` is true and `is_symlink()`
    is false). A symlink already pointing at `source` is left alone too — this is what makes
    linking twice a no-op. Everything else — nothing there, or a symlink pointing anywhere
    else, dangling included — is replaced.
    """
    if target.exists() and not target.is_symlink():
        return False
    if target.is_symlink() and target.readlink() == source:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        target.unlink()
    target.symlink_to(source, target_is_directory=source.is_dir())
    return True


def _index_source(store: Store, config: Config, machine: Path | None) -> Path | None:
    """The index's own §9.1 target rule — the same one `store.py`'s `_group_targets` applies
    to every configured group, applied here because nothing upstream applies it to `MEMORY.md`.

    A missing or dangling index sources nothing, same as before. A real file sources itself,
    unconditionally, same as before. A symlink is new: outside overlay mode it is refused
    outright (there is no overlay to validate it against, exactly like an ungoverned group
    symlink); in overlay mode it is honoured only when it resolves inside this project's own
    share of the recorded overlay (`permitted_roots`) — never a different project's.
    """
    target = store.path / INDEX_NAME
    if not target.exists():
        return None
    if not target.is_symlink():
        return target.resolve()
    if store.mode != "overlay":
        return None
    overlay = overlay_root(machine)
    if overlay is None:
        return None
    allowed = permitted_roots(overlay, config.project.name)
    resolved = target.resolve()
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed):
        return None
    return resolved


def link(
    worktree: Path,
    store: Store,
    config: Config,
    *,
    home: Path | None = None,
    machine: Path | None = None,
) -> list[Path]:
    """Create what is missing and return it; already-correct links are not re-made.

    A no-op for the main checkout itself: it already holds the real store, not a link to it,
    so there is nothing for this function to do there. `machine` is threaded through only to
    validate a symlinked index in overlay mode (`_index_source`); pass the same value used to
    resolve `store` in the first place, or the two can disagree about where the overlay is.
    """
    if main_checkout(worktree).resolve() == worktree.resolve():
        return []
    created: list[Path] = []
    base = worktree / config.paths.memory
    base.mkdir(parents=True, exist_ok=True)
    sources: dict[str, Path] = dict(store.groups)
    index_source = _index_source(store, config, machine)
    if index_source is not None:
        sources[INDEX_NAME] = index_source
    for name in linked_names(config):
        source = sources.get(name)
        if source is None:
            continue
        target = base / name
        if _link(source.resolve(), target):
            created.append(target)
    harness = harness_memory_path(worktree, home)
    if _link(store.path.resolve(), harness):
        created.append(harness)
    return created
