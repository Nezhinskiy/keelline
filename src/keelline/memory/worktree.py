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
project-memory link is read by the harness's own memory reader, outside both — so it is the one
hop that leaves this lane's gate entirely, and the one place where asking the gate a slightly
wrong question costs everything the gate was for. `link` asks it about the directory the link
exposes, which in overlay mode is repository data even though the notes are not; see the note
on `link` itself.

**And it asks in both directions.** A gate evaluated once, at creation, over state that
persists is not a gate: `~/.claude/projects/<slug>/memory` outlived the record that authorised
it, so a `git pull` that adds a note to a trusted in-repo store lapses the record, closes every
channel this lane controls — and left the one channel it does not controlling a live link to
the new bytes. `link` therefore removes that link when the gate now answers False, in the same
call that would have created it: it already knows both facts, and the only state it may act on
is a symlink pointing at this store, never a real directory and never somebody else's link.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from keelline import fsops
from keelline.config.paths import contained
from keelline.config.schema import Config
from keelline.errors import Failure, Refusal
from keelline.memory import trust
from keelline.memory.index import INDEX_NAME, index_source
from keelline.memory.store import (
    Store,
    in_repository,
    main_checkout,
    overlay_group_target,
    overlay_root,
    permitted_roots,
    resolve,
)

OVERLAY_MODE = "overlay"


class PartialLink(OSError):
    """An `OSError` part-way through `link`, carrying the links that were already made.

    Links are created one at a time, so a failure half way through leaves the tree holding
    some names and not the rest — and per this module's docstring above, a group missing from
    the tree is also missing from the floor the reference guard derives from it: invisible
    twice. The `SessionStart` handler degrades open, which is right (a memory handler never
    costs a session), but degrading open on a bare `OSError` threw `created` away with the
    exception, so nothing anywhere could say that half a tree existed.

    An `OSError` and not a `Refusal`: nothing crossed a boundary here, a write failed. A
    `PathEscape` from `contained` still leaves this function as itself, and the caller decides
    separately what a containment refusal means — see `keelline.memory.hooks`.
    """

    def __init__(self, created: Sequence[Path], cause: OSError) -> None:
        super().__init__(str(cause))
        self.created = list(created)


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


def _unlink(source: Path, target: Path) -> bool:
    """Remove a symlink this module made; report whether it did anything.

    The mirror of `_link`, and deliberately narrower than it. Only a symlink whose own target
    is `source` is removed: a real file or directory is unmerged work or a store the harness
    created on its own, and a symlink pointing anywhere else belongs to somebody else — the
    same two things `_link` refuses to clobber. Withdrawing a link is not licence to delete a
    directory. A *dangling* link at `source` is still this module's own and still goes: what
    the gate refuses is the name, not the bytes behind it.
    """
    if not target.is_symlink() or target.readlink() != source:
        return False
    target.unlink()
    return True


@dataclass(frozen=True)
class Links:
    """What `link` changed: the links it made, and the harness link it withdrew.

    Two lists and not one, because the caller says different things about them. `created` is
    "this worktree can now see the store"; `revoked` is "the harness can no longer see it,
    because the owner's approval has lapsed" — a security-relevant event, and the sort of
    thing this module's own history says must never be silent. A run that revokes reports no
    creations, so folding them together would render a revocation as "linked 1 path".
    """

    created: list[Path] = field(default_factory=list)
    revoked: list[Path] = field(default_factory=list)


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


def link(worktree: Path, store: Store, config: Config, *, home: Path | None = None) -> Links:
    """Create what is missing, withdraw what is no longer authorised, and report both.

    A no-op for the main checkout itself: it already holds the real store, not a link to it,
    so there is nothing for this function to do there. Validating a symlinked index in overlay
    mode (`index.index_source`) needs the machine file, and takes it from `store.machine`, so
    the two can no longer disagree about where the overlay is.

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

    The condition is `trust.may_inject`, and it must be asked **about the directory this link
    exposes**, which is what `repository_data=in_repository(store, store.path)` says. Asked
    without that argument it fell through `inside_project(store)`, and in overlay mode that is
    False by design — every group resolves out into the overlay — while `store.path` is a real
    directory *inside the repository*. So a clone shipping a committed `docs/memory/MEMORY.md`
    got the harness link created for it on no trust record at all, and the harness's own
    **native** memory reader then injected the file with no delimiter, no nonce and no gate.
    `bundles.blocks` correctly returned `[]` for the same store in the same session: this lane
    refused to inject the file through the channel it controls, and created the link to the
    channel it does not.

    `bundles.blocks` already knew to ask the wider question and passes
    `repository_data=in_repository(store, source)`. The difference here is only *what* is being
    exposed: a link to a directory exposes every file under it, so the question is whether the
    **directory** is repository data, not whether the notes are.

    Nothing narrower than `may_inject` will do. It is already the predicate that means "these
    bytes may reach the model at all": it short-circuits to True when neither
    `inside_project(store)` nor `repository_data` holds, so the machine owner's own overlay
    notes keep their link with no record at all, and otherwise it demands a digest that matches
    what the owner approved. Gating on `inside_project` alone would ask the wrong question (it
    would refuse a trusted store for ever); gating on the mode would ask the clone.

    **The same gate runs in the other direction, in the same call.** Creation was gated and
    removal was not, so the link outlived the record that authorised it: `record`, then a
    `git pull` adding one note, and `state(...).trusted` is False, `blocks(...)` is `[]` —
    every channel this lane controls correctly shut — while `~/.claude/projects/<slug>/memory`
    still pointed at the store the new note is in, and the harness's native reader still read
    it with no gate, no delimiter and no trust record. A gate asked once about state that
    persists is not a gate. `_unlink` is deliberately narrower than `_link`: only a symlink
    already pointing at this store is withdrawn, because refusing to expose a directory is not
    licence to delete one.

    Raises `PartialLink` — an `OSError` carrying the links already made — when a write fails
    part-way, rather than letting `created` die with the exception. The caller degrades open;
    it needs to be able to say which half of the tree exists while it does. The withdrawal is
    last, so a failure there carries out the creations and revokes nothing.
    """
    if main_checkout(worktree).resolve() == worktree.resolve():
        return Links()
    created: list[Path] = []
    revoked: list[Path] = []
    try:
        base = _tree_base(worktree, store)
        if base is not None:
            base.mkdir(parents=True, exist_ok=True)
            sources: dict[str, Path] = dict(store.groups)
            found = index_source(store, config)
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
        harness = harness_memory_path(worktree, home)
        if harness_link_needed(store, config):
            if _link(store.path.resolve(), harness):
                created.append(harness)
        elif _unlink(store.path.resolve(), harness):
            revoked.append(harness)
    except OSError as exc:
        raise PartialLink(created, exc) from exc
    return Links(created, revoked)


def harness_link_needed(store: Store, config: Config) -> bool:
    """Whether `~/.claude/projects/<slug>/memory` may point at this store — asked in one place.

    `link` asks it for a worktree, `attach_main` asks it for the owning checkout, and `attach`
    asks it again before taking §6.3's settings-file fallback. Three callers and one spelling,
    because the question is easy to ask slightly wrong and asking it wrong costs everything the
    gate was for: `repository_data=in_repository(store, store.path)` is what makes it a question
    about *the directory this link exposes* rather than about the notes behind it. Asked without
    that argument it falls through `inside_project(store)`, which is False in overlay mode by
    design while `store.path` is a real directory inside the repository — and a clone shipping a
    committed store then gets the link created for it on no trust record at all.
    """
    return trust.may_inject(store, config, repository_data=in_repository(store, store.path))


def attach_main(
    root: Path,
    store_path: Path,
    config: Config,
    *,
    machine: Path | None = None,
    home: Path | None = None,
) -> Links:
    """Build the link tree in the checkout that owns the store, in overlay mode (§6.3).

    The case `link` excludes. `link` is right that the main checkout "already holds the real
    store, not a link to it" in `local-only` and `in-repo`; in `overlay` mode §6.2 puts the real
    store in the overlay and the checkout holds a tree of links, so the owning checkout needs an
    entry point of its own. It lives here rather than in `attach` because the two share `_link`,
    `_unlink` and the gate above, and a second copy of that gate in another area is the most
    expensive duplication this plan could make.

    **It takes a `store_path` and not a resolved `Store`, because there is nothing to resolve
    yet:** in overlay mode `resolve()` reads the link tree, and the link tree is what this
    function creates. So the links come first and `resolve()` second, which is also why the
    harness link is last.

    The overlay root comes from `overlay_root(machine)` and never from `store_path` (DP3), and
    `store_path` is checked against `permitted_roots` rather than trusted — `attach` refuses the
    same store one layer up, and this is the floor under that.

    Raises `PathEscape` rather than skipping when a group name leaves the tree, for the reason
    `link` gives: `memory.groups` is repository-controlled and skipping one escaping name leaves
    the next free to try the same thing.
    """
    if config.memory.mode != OVERLAY_MODE:
        raise Refusal(
            f"memory.mode is {config.memory.mode!r}, so this repository holds its own store and "
            f"there is no tree of links to build; only an overlay-mode repository is attached"
        )
    overlay = overlay_root(machine)
    if overlay is None:
        raise Refusal(
            "no overlay root is recorded in the machine configuration, so there is nothing to "
            "link into; run `keelline setup` first"
        )
    if store_path.resolve() != permitted_roots(overlay, config.project.name)[1].resolve():
        raise Refusal(
            f"{store_path} is not this project's own share of the recorded overlay "
            f"({permitted_roots(overlay, config.project.name)[1]}); linking there would put "
            f"another project's notes into this session"
        )
    base = contained(root, config.paths.memory)
    created: list[Path] = []
    revoked: list[Path] = []
    try:
        # `mkdirs_within` creates a target's *parents* through the `O_NOFOLLOW` walk, so the
        # store directory is asked for as the parent of the index link that goes into it.
        fsops.mkdirs_within(root, f"{config.paths.memory}/{INDEX_NAME}")
        for name in linked_names(config):
            source = (
                store_path / INDEX_NAME
                if name == INDEX_NAME
                else overlay_group_target(overlay, config.project.name, name)
            )
            # `allow_final_symlink`, because replacing a wrong or dangling symlink already
            # sitting at the target is this function's job; every level above it is not.
            target = contained(base, name, allow_final_symlink=True)
            if _link(source, target):
                created.append(target)
        store = resolve(root, config, machine=machine)
        if store is None:
            raise Failure(
                "the link tree was created and the store still does not resolve; "
                "`keelline memory index --check` reports why"
            )
        harness = harness_memory_path(root, home)
        if harness_link_needed(store, config):
            if _link(store.path.resolve(), harness):
                created.append(harness)
        elif _unlink(store.path.resolve(), harness):
            revoked.append(harness)
    except OSError as exc:
        raise PartialLink(created, exc) from exc
    return Links(created, revoked)


def detach_main(root: Path, config: Config, *, home: Path | None = None) -> Links:
    """Withdraw the link tree a checkout holds, and the harness link with it (§6.3).

    The mirror of `attach_main`, and here for the same reason: `_unlink` is deliberately
    narrower than `_link` — only a symlink whose own target is this store is removed, because a
    real directory at one of these names is unmerged work or a store the harness made, and
    withdrawing a link is not licence to delete a directory. A second copy of that rule in the
    attach area is the duplication this module's own history argues against.

    The harness link goes first, because it is the one hop that leaves this lane's gate, and it
    is compared against the store directory rather than against what it happens to point at.

    Takes a `Config` and not a `Store`: by the time a repository is detached its store may no
    longer resolve — that is half of what detaching means — so the tree is found where the
    configuration says it is and each name is removed only if it is one of ours.
    """
    base = contained(root, config.paths.memory, allow_final_symlink=True)
    revoked: list[Path] = []
    harness = harness_memory_path(root, home)
    if _unlink(base.resolve(), harness):
        revoked.append(harness)
    for name in linked_names(config):
        target = contained(base, name, allow_final_symlink=True)
        if not target.is_symlink():
            continue
        # Through the `O_NOFOLLOW` walk, so a component that became a symlink after
        # `contained()` passed cannot redirect the removal out of the checkout.
        fsops.remove_within(root, f"{config.paths.memory}/{name}")
        revoked.append(target)
    return Links([], revoked)
