"""Where the notes are, and the four ways that answer can be a lie (§9.1).

A store is a per-project value with no machine-level default, because the wrong answer is not
"no memory" but *another project's* memory reaching this session. Four things are therefore
checked, and each closes a hole the other three leave open:

1. **The shape.** In overlay mode `paths.memory` is a real directory holding one link per
   group (§6.3). It is not one link: `developer` points into the overlay's `common/memory`,
   which is shared across projects and cannot live under `projects/<name>/`. A single link at
   `paths.memory` would lose the cross-project half of the store outright.
2. **Containment inside the store.** A group name is repository-controlled — `memory.groups`
   is an ordinary `keelline.toml` list — so `groups = ["../secret"]` must not become a read,
   and certainly not a write, outside the store. `config/paths.py` says in as many words that
   this field reaches no guard of its own and that the lane consuming it owns the check.
3. **The link's target.** A link is honoured only when it lands inside *this project's* share
   of the recorded overlay: `common/memory`, or `projects/<the bound name>/memory`. Testing
   containment in the overlay root alone lets an honestly-named, honestly-bound project point
   one directory sideways at another client's notes.
4. **The binding.** The overlay's `projects/<name>/project.toml` must record this
   repository's own `origin`. `git` runs with a scrubbed environment, because an inherited
   `GIT_DIR` would otherwise answer for a different repository altogether.

**What the environment can and cannot choose.** The store's *location* is never named by a
variable this process reads: `resolve` takes an `env` mapping and ignores it by contract, and
`_git` runs with a scrubbed environment, so neither a `KEELLINE_STORE`-shaped variable nor an
inherited `GIT_DIR` can point this module at another project's notes. Both halves are pinned
by tests, and both matter because a committed `.claude/settings.json` may carry an `env` block
that applies with no trust prompt in a non-interactive session.

**The machine file makes the same claim now.** `machine_config_path` gates `KEELLINE_CONFIG`
behind `interactive` — and `XDG_CONFIG_HOME` with it, which it did not, and which made the
first gate worth nothing: both variables reach the same file and this lane routes §9.1's
overlay anchor (`overlay_root(None)`) and §9.4's trust record (`trust._trust_file(None)`)
through it. A committed `env` block therefore chose which overlay root `permitted_roots` was
computed from, and which `trust.json` `may_inject` consulted, wherever no `--machine` was
threaded.

Stated exactly, because the exposure was not the same size as the invariant it broke: pointing
a variable somewhere of the author's choosing **suppressed** memory — no overlay root and no
recorded digest means overlay stores refuse to resolve and the gate fails closed — while making
it *grant* anything additionally required a pre-recorded hash matching a digest of the store at
the clone's absolute path, which is the key `trust` records under. No injection was ever built
from it. It was still a hole in an invariant two other properties lean on, and closing it in
`config/machine.py` — the foundation's file — is what makes the claim above about `env` a claim
about the whole module rather than about `resolve` alone.
"""

from __future__ import annotations

import os
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from keelline.config.machine import machine_config_path
from keelline.config.paths import PathEscape, contained
from keelline.config.schema import Config

LOCAL_STORE = Path(".keelline") / "local" / "memory"
PROJECT_RECORD = "project.toml"
COMMON = Path("common") / "memory"
_GIT_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT")
# Wall-clock bound on one `_git` call (D7: a cap, not read from config.budgets or
# config.native_caps — no shipped file needs to change with it). Every call this module makes
# is a local, argument-free, read-only query (`rev-parse`, `remote get-url`) against a
# scrubbed environment, so it never touches the network; this only guards against a `git`
# binary that hangs outright, and is generous for that without leaving store resolution
# blocked for long.
_GIT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Store:
    path: Path
    mode: str
    root: Path
    groups: dict[str, Path] = field(default_factory=dict)
    # Per-group refusal prose from `_group_targets`, built the same way `refusal_reason` builds
    # its message: it embeds the raw `memory.groups` entry, a field with no schema constraint
    # (a TOML multi-line string carries literal newlines through unchanged). Same hazard, same
    # rule — never put a value out of this dict into model context unwrapped; `trust.wrap` it
    # first if a consumer must show the detail.
    unavailable: dict[str, str] = field(default_factory=dict)

    def group_dir(self, group: str) -> Path | None:
        return self.groups.get(group)


def _git(root: Path, *args: str) -> str | None:
    env = {key: os.environ[key] for key in _GIT_ENV_KEEP if key in os.environ}
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None


def main_checkout(root: Path) -> Path:
    """The checkout that owns the store, for a session running inside a worktree.

    The result must be an ancestor of nothing and a sibling of anything — but it must be a
    real git answer, not one an inherited `GIT_DIR` produced, which is why `_git` scrubs.
    """
    common = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common).parent if common else root


_WORKTREES = "worktrees"
_BACK_POINTER = "gitdir"


def _registered_worktree(root: Path) -> Path | None:
    """The checkout `root` is genuinely a registered worktree of, or `None` when it is not one.

    The fallback used to require the worktree to live *under* the main checkout, and that
    killed the feature in git's own documented layout: `git worktree add ../side` puts the
    tree beside the checkout, containment was False, and `resolve` answered that there was no
    store at all — so nothing was ever linked in the one place this module exists for.

    **Registration is the question containment was standing in for.** A linked worktree's
    private git directory is `<common-dir>/worktrees/<name>`, and that directory holds a
    `gitdir` file naming the `.git` file the worktree was created for. Both halves are
    checked, because only the first is written by whoever owns `root`: a `.git` may be a plain
    text pointer, so any directory can *claim* to be a worktree of a repository it was never
    added to, and `git rev-parse` will answer for that repository. The back-pointer is the
    half the claimed repository wrote. (A clone cannot ship either — git refuses to track a
    path named `.git` — but the fallback reads a store out of another repository, so it does
    not rest on that.)

    Both queries go through `_git`, which scrubs the environment. That is a second lock on the
    same door rather than this one's support: an inherited `GIT_DIR` answers for whatever
    repository it names, and there it is also its own common dir, so a redirected fallback
    fails the registration test above anyway. Because they are redundant, each is pinned by its
    own test rather than by one that dies only when both are gone —
    `test_an_inherited_git_dir_never_reaches_the_git_helper` for the scrubbing and
    `test_a_directory_that_merely_sits_under_a_checkout_is_not_a_worktree_of_it` for this.
    """
    common = _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    private = _git(root, "rev-parse", "--path-format=absolute", "--git-dir")
    if common is None or private is None:
        return None
    common_dir, private_dir = Path(common).resolve(), Path(private).resolve()
    if private_dir.parent != common_dir / _WORKTREES:
        return None
    try:
        recorded = (private_dir / _BACK_POINTER).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not recorded or Path(recorded).parent.resolve() != root.resolve():
        return None
    owner = common_dir.parent
    return None if owner == root.resolve() else owner


def overlay_root(machine: Path | None) -> Path | None:
    path = machine_config_path(interactive=False) if machine is None else machine
    if not path.is_file():
        return None
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    section = raw.get("overlay")
    if not isinstance(section, dict):
        return None
    value = section.get("root")
    return Path(str(value)).expanduser() if isinstance(value, str) and value else None


def _bound(overlay: Path, project: str, root: Path) -> bool:
    record = overlay / "projects" / project / PROJECT_RECORD
    if not record.is_file():
        return False
    try:
        raw = tomllib.loads(record.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    recorded = raw.get("remote")
    if not isinstance(recorded, str) or not recorded:
        return False
    return _git(root, "remote", "get-url", "origin") == recorded


def _inside(candidate: Path, parent: Path) -> bool:
    resolved = candidate.resolve()
    base = parent.resolve()
    return resolved == base or base in resolved.parents


def permitted_roots(overlay: Path, project: str) -> tuple[Path, Path]:
    """This project's whole share of the overlay: the common notes and its own (§6.2)."""
    return overlay / COMMON, overlay / "projects" / project / "memory"


def _declared(root: Path, config: Config) -> Path | None:
    try:
        return contained(root, config.paths.memory, allow_final_symlink=True)
    except PathEscape:
        return None


def _group_targets(
    base: Path, config: Config, overlay: Path | None
) -> tuple[dict[str, Path], dict[str, str]]:
    groups: dict[str, Path] = {}
    unavailable: dict[str, str] = {}
    for group in config.memory.groups:
        try:
            target = contained(base, group, allow_final_symlink=True)
        except PathEscape as exc:
            unavailable[group] = str(exc)
            continue
        if not target.exists():
            unavailable[group] = f"{group} is not in the store"
            continue
        if target.is_symlink():
            if overlay is None:
                unavailable[group] = f"{group} is a link and no overlay is recorded"
                continue
            allowed = permitted_roots(overlay, config.project.name)
            if not any(_inside(target, permitted) for permitted in allowed):
                unavailable[group] = (
                    f"{group} links outside this project's share of the overlay "
                    f"({', '.join(str(p) for p in allowed)})"
                )
                continue
        groups[group] = target
    return groups, unavailable


def _resolve_at(
    root: Path, config: Config, override: str | None, machine: Path | None
) -> tuple[Store | None, str | None]:
    mode = config.memory.mode
    overlay = overlay_root(machine)
    if override is not None:
        base = Path(override).expanduser()
    elif mode == "local-only":
        try:
            # `contained` with no `allow_final_symlink` refuses a symlink at *any* level
            # between the root and the target, which testing `base.is_symlink()` did not:
            # `.keelline` and `.keelline/local` were never looked at, and a group directory
            # reached *through* one of those is not itself a symlink, so the per-group check
            # below never ran either. That is the same hazard the comment below documents for
            # `paths.memory`, left open one directory higher — and in the mode the preset
            # ships by default, where the whole store is otherwise ungoverned by `contained`.
            base = contained(root, str(LOCAL_STORE))
        except PathEscape as exc:
            return None, f"{exc}; local-only memory must be a real directory"
    else:
        declared = _declared(root, config)
        if declared is None:
            return None, f"paths.memory ({config.paths.memory!r}) does not stay inside the project"
        base = declared
        # §9.1 check 1: in every mode but `local-only` and an explicit `override`, `paths.memory`
        # itself must be a real directory — one link per group, not one link for the whole
        # store. This has to hold in overlay mode too, not just `in-repo`: a group directory
        # reached *through* a symlinked `paths.memory` is not itself a symlink, so the per-group
        # check below (`permitted_roots`) never runs, and the whole store silently becomes
        # whatever `paths.memory` was pointed at — including another project's share.
        if declared.is_symlink():
            return None, (
                f"{config.paths.memory} is a symlink; {mode} memory must be a real directory"
            )
    if mode == "overlay":
        if overlay is None:
            return (
                None,
                "no overlay root is recorded in the machine configuration; run `keelline setup`",
            )
        if not _bound(overlay, config.project.name, root):
            return None, (
                f"the overlay does not record this repository's origin remote for project "
                f"{config.project.name!r}; run `keelline attach`"
            )
    if not base.is_dir():
        return None, f"{base} does not exist; run `keelline attach`"
    groups, unavailable = _group_targets(base, config, overlay if mode == "overlay" else None)
    if not groups:
        reason = "; ".join(f"{k}: {v}" for k, v in unavailable.items()) or "the store has no groups"
        return None, reason
    return Store(base, mode, root, groups, unavailable), None


def resolve(
    root: Path,
    config: Config,
    *,
    override: str | None = None,
    machine: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Store | None:
    # `env` is accepted and never read: §9.1 forbids selecting a store through the
    # environment, and a parameter that exists and is ignored is a claim a test can pin.
    del env
    store, _ = _resolve_at(root, config, override, machine)
    if store is not None:
        return store
    # A worktree resolves through the checkout it is *registered against*, never through
    # whatever a redirected `GIT_DIR` named and never merely because a directory sits above it.
    parent = _registered_worktree(root)
    if parent is None:
        return None
    store, _ = _resolve_at(parent, config, override, machine)
    return store


def refusal_reason(
    root: Path,
    config: Config,
    *,
    override: str | None = None,
    machine: Path | None = None,
) -> str | None:
    """Why `resolve` returned no store for this call, or `None` when it would not have refused.

    The string is built out of `memory.groups` entries (`_group_targets`'s `unavailable`
    messages) and out of `config.paths.memory`, both repository-controlled and neither
    schema-constrained — a TOML multi-line string carries literal newlines through unchanged,
    so this can come back multi-line, and the same repository text can appear in it twice. It
    must never reach model context unwrapped: see `keelline.memory.hooks`, this lane's own
    consumer, which refuses to put this text into `HookResult.context` for exactly that reason.
    A consumer that must show the detail wraps it first with `trust.wrap`.
    """
    store, reason = _resolve_at(root, config, override, machine)
    if store is not None:
        return None
    parent = _registered_worktree(root)
    if parent is not None:
        upstream, upstream_reason = _resolve_at(parent, config, override, machine)
        return None if upstream is not None else upstream_reason
    return reason


def inside_project(store: Store) -> bool:
    """Whether any note actually lives in the repository — the predicate §9.4 turns on.

    Not `memory.mode`, which the clone chooses, and not the store directory, which in overlay
    mode is a real directory of links inside the project. What decides whether a note is the
    machine owner's or the repository's is where the note itself sits: `local-only` puts it
    under `.keelline/local/`, which a `.gitignore` keeps out of a clone the owner made and
    does not keep out of a clone the attacker authored.

    This asks the question of the *notes*, and deliberately keeps asking only that. Folding
    `store.path` in would make every overlay store repository data — the store directory is a
    real directory in the repository in exactly that mode — and so would gate the machine
    owner's own overlay notes behind a trust prompt and wrap them as data, defeating every
    standing rule in the mode this project actually ships. A file that is not a note and
    belongs to no group is asked about one at a time, with `in_repository` below.

    **Where it cannot answer, it answers closed.** In `local-only` and `in-repo` the notes are
    in the repository by construction — `.keelline/local/memory` and `paths.memory` are both
    resolved under `root` through `contained`, which refuses a symlink at every level — so a
    group landing outside `store.root` in those modes is a resolution that went wrong, not a
    store belonging to the machine owner. Answering False there is what let a clone that
    escaped the resolver reach the model with no trust record and no `trust.wrap`: a gate
    whose default for the unclassifiable is "ungated" is the wrong way round. `overlay` keeps
    its answer, because outside `store.root` is precisely where §6.2 puts those notes.
    """
    if any(_inside(target, store.root) for target in store.groups.values()):
        return True
    return store.mode != "overlay"


def in_repository(store: Store, path: Path) -> bool:
    """Whether one particular file this store yields sits in the repository itself.

    `inside_project` cannot answer this for `MEMORY.md`: the index is not a note, belongs to no
    `memory.groups` entry and lives at `store.path`, which in overlay mode is inside the
    repository while every group resolves far outside it. A caller that is about to inject a
    specific file asks about that file.
    """
    return _inside(path, store.root)
