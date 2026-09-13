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

That rule lives in `index.index_source`, not here, because linking is not its only reader:
`bundles._index` reads the same file and injects it into the model, which is the channel that
matters more. Two copies of one boundary rule is one copy too many.

One of the two gaps is not like the other. The links inside the worktree are read by this
lane's own bundles, which gate on `trust.may_inject` and wrap what they emit; the harness
project-memory link is read by the harness's own memory reader, outside both. `link` therefore
asks the gate before it makes that one — see the note on `link` itself.
"""

from __future__ import annotations

from pathlib import Path

from keelline.config.paths import contained
from keelline.config.schema import Config
from keelline.memory import trust
from keelline.memory.index import INDEX_NAME, index_source
from keelline.memory.store import Store, main_checkout


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


def _tree_base(worktree: Path, store: Store) -> Path | None:
    """Where the worktree's copy of the link tree belongs: the store's own place in the checkout.

    Derived from `store`, never from `config.paths.memory`. Both halves of that matter. The
    value is repository-controlled and reaches no guard that resolves it — `validate_paths`
    passes `allow_final_symlink=True` for `memory` and `contained()` does not resolve a final
    component — so a committed symlink there loads without complaint, and `mkdir(parents=True)`
    followed it out of the checkout onto any directory the author chose. And it is not even the
    right answer: `local-only`, the preset default, resolves the store at `.keelline/local/`
    and never consults `paths.memory`, so a tree built there landed where no reader looks and
    outside the `.gitignore` entry that mode relies on. The store already knows where it is.

    `None` means there is nothing to mirror: `--store` may point the store anywhere, and a
    store outside its own root has no counterpart position inside a worktree to build. That is
    a skip rather than a refusal — nothing escaped, there is simply no such directory — while a
    `relative` that leaves the worktree *is* a refusal, raised by `contained`.
    """
    try:
        relative = store.path.relative_to(store.root)
    except ValueError:
        return None
    if not relative.parts:
        return None
    return contained(worktree, str(relative))


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
    validate a symlinked index in overlay mode (`index.index_source`); pass the same value
    used to resolve `store` in the first place, or the two can disagree about where the
    overlay is.

    Raises `PathEscape` rather than skipping when a name leaves the tree. Every `name` here is
    repository-controlled (`memory.groups` is an ordinary `keelline.toml` list, and §7.4 says
    in as many words that it reaches no guard of its own), and `store.groups` was validated
    against the *main checkout's* tree — a worktree is a separate checkout of a separate
    branch, so its own copy of that subtree can hold a symlink the main one does not. Skipping
    one escaping name would leave the next name in the list free to try the same thing.

    **The harness link is the one hop that leaves keelline's gate, so it is the one that asks
    about trust.** Every link above lands inside the worktree, where the only reader is this
    lane's own `bundles.blocks` — which calls `trust.may_inject` and wraps what it emits in
    `trust.wrap`'s nonce region. `~/.claude/projects/<slug>/memory` is read by the *harness's*
    native memory reader instead: whatever sits behind it reaches the model with no gate, no
    delimiter and no trust record. In `local-only` — the preset default — and in `in-repo` the
    store is content the clone shipped, so creating that link before the owner has said
    `keelline memory trust --in-repo-memory` hands repository-authored text to the model
    through a channel this lane does not control.

    The condition is `trust.may_inject(store, config, machine=machine)` and nothing narrower.
    It is already the predicate that means "these bytes may reach the model at all": it
    short-circuits to True when `inside_project(store)` is False, so the machine owner's own
    overlay notes keep their link with no record at all, and otherwise it demands a digest that
    matches what the owner approved. Gating on `inside_project` alone would ask the wrong
    question (it would refuse a trusted store for ever); gating on the mode would ask the
    clone.
    """
    if main_checkout(worktree).resolve() == worktree.resolve():
        return []
    created: list[Path] = []
    base = _tree_base(worktree, store)
    if base is not None:
        base.mkdir(parents=True, exist_ok=True)
        sources: dict[str, Path] = dict(store.groups)
        found = index_source(store, config, machine)
        if found is not None:
            sources[INDEX_NAME] = found
        for name in linked_names(config):
            source = sources.get(name)
            if source is None:
                continue
            # `allow_final_symlink`, because replacing a wrong or dangling symlink already
            # sitting at the target is this function's job; every level above it is not.
            target = contained(base, name, allow_final_symlink=True)
            if _link(source.resolve(), target):
                created.append(target)
    if not trust.may_inject(store, config, machine=machine):
        return created
    harness = harness_memory_path(worktree, home)
    if _link(store.path.resolve(), harness):
        created.append(harness)
    return created
