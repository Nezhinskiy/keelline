"""What `keelline attach` actually writes, in the order the refusals have to happen in.

**Four things this module does not build.**

*Not a hook-entry merger.* `keelline.scaffold` already exports `apply_entries`, `mark` and
`owned_ids`, and it inherits the two rules a hand-rolled merge gets wrong: a group mixing a
marked entry with a foreign one is **split, not replaced**, and a shape it cannot read is
**refused, not filtered**, because "dropping a group it did not recognise deletes somebody
else's hook and says nothing".

*Not C2's `plan`/`apply` for the settings file.* The engine stamps a digest of the document into
the **committed** `.keelline/manifest.json`, which would publish a digest of the owner's personal
allow rules to every collaborator. The pure functions are called instead — document string in,
document string out, no manifest — and the ledger below takes the manifest's place. This is the
one place where refusing an existing mechanism is right.

*Not one id for every entry.* `owned_ids` returns `dict[str, str]`, so one shared
`keelline:overlay` id yields exactly one provenance row however many entries there are, and the
same id under two events keeps only the last. `permissions.overlay_entries` numbers them
`overlay-<event>-<n>`, one per entry.

*Not a pretence that the two halves are symmetric (DP4).* A hook entry's `# keelline:<id>` lives
inside its command string, so it has an in-band witness that survives the file being edited by
hand. A `permissions.allow` string cannot carry one — `scaffold.mark` appends to a *command* —
so an allow rule has exactly **one** witness, the ledger at `.keelline/local/attach.json`, and
`detach` is only ever as good as that file.

**The ledger is written under `.keelline/local/`, and the `.gitignore` region goes first.** The
repository has no `.keelline` line today and the lane that would ship one is out of scope, so
without that region `attach` drops the owner's personal allow rules into a tracked-by-default
path. It is written before the ledger rather than beside it, so the ledger is never in a tracked
path even for an instant — and if the region cannot be written, writing the ledger would be a
leak, so the answer is a refusal rather than a warning.

**Every write goes through a primitive that already exists.** `fsops.write_within(root, …)` for
everything inside the project and `fsops.write_within(overlay, …)` for the binding record — the
overlay root is a root, so there is no carve-out to take anywhere here.
"""

from __future__ import annotations

import datetime
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from keelline import fsops, tomlout
from keelline.attach.binding import MISMATCH, Binding, read_binding
from keelline.attach.permissions import (
    LOCAL_SETTINGS,
    PermissionDiff,
    codex_rules,
    diff_permissions,
    local_document,
    overlay_entries,
    settings_document,
)
from keelline.config.loader import load
from keelline.config.schema import Config
from keelline.errors import Failure, Refusal
from keelline.fsops import UnsafePath
from keelline.gitenv import git_run
from keelline.guards.api import hooks_dir
from keelline.memory.api import (
    COMMON_GROUP,
    PROJECT_RECORD,
    PROJECTS,
    Links,
    attach_main,
    detach_main,
    harness_link_needed,
    harness_memory_path,
    link,
    main_checkout,
    resolve,
)
from keelline.overlay.api import Runner
from keelline.scaffold import (
    EntriesError,
    Style,
    apply_entries,
    drop,
    marker_id,
    owned_ids,
    upsert,
)

LEDGER = ".keelline/local/attach.json"
LEDGER_FORMAT = 1
GITIGNORE = ".gitignore"
IGNORE_REGION = "ignore"
# §7.1 lists both: the ledger's directory, and the assessment file `assess` will write.
IGNORED = (".keelline/local/", ".keelline/assessment.json")
IGNORE_NOTE = "# Keelline's local state: yours, never a collaborator's."
PRE_COMMIT_CONFIG = ".pre-commit-config.yaml"
# The hook's *name*; where it lives is `guards.hooks_dir`'s answer and not `.git/hooks`. An
# overlay with `core.hooksPath` set -- a common global dotfiles setting -- or one that is a
# worktree or a submodule, where `.git` is a file, has its hooks somewhere else entirely, and a
# hardcoded path finds the scan missing on every attach and shells out to `pre-commit install`
# every time. `docs/cli.md`'s `setup --git-hooks` section states the rule this now follows:
# `git rev-parse --git-path hooks`, never `core.hooksPath`.
PRE_COMMIT_HOOK = "pre-commit"
# §6.3's fallback for the one link that leaves Keelline's own channel: "a settings-file value is
# subject to workspace trust and a link is not", so the symlink is preferred and this is taken
# only when it cannot be made.
FALLBACK_KEY = "autoMemoryDirectory"
# `fsops.mkdirs_within` creates a target's *parents*, so a directory is asked for as the parent
# of a name inside it. Nothing is ever written at this name; `overlay.create` asks the same way.
_INSIDE = ".keep"


@dataclass(frozen=True)
class Attached:
    """What one `attach` changed. Nothing here is repository-authored, so all of it may print."""

    settings_written: bool
    rules_written: tuple[str, ...]
    binding_recorded: bool
    ignored: bool
    notes: tuple[str, ...]
    links: Links


@dataclass(frozen=True)
class AttachLedger:
    """The only witness an allow rule has (DP4), and the authority `detach` reads.

    `entries` maps each marker id to its event, which is the shape `scaffold.owned_ids` answers
    in, so `doctor` can compare the two without a translation in between.
    """

    store: str
    allow: tuple[str, ...]
    entries: dict[str, str]
    rules: tuple[str, ...]
    settings_keys: tuple[str, ...]


def ledger(root: Path) -> AttachLedger:
    """The ledger this repository's last `attach` wrote, or a `Failure` naming the missing file.

    Never a best effort. Guessing which allow rules were Keelline's from their content is the
    heuristic this file exists to replace, and a `detach` built on a guess removes a rule the
    owner wrote by hand — which is worse than removing none.
    """
    path = root / LEDGER
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise Failure(
            f"{LEDGER} is not there, so nothing records what `keelline attach` added to this "
            f"repository; there is no safe way to guess it from the settings file"
        ) from exc
    except OSError as exc:
        raise Failure(f"{path} cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise Failure(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise Failure(f"{path} is not a JSON object")
    entries = raw.get("entries")
    return AttachLedger(
        store=str(raw.get("store", "")),
        allow=tuple(r for r in raw.get("allow", []) if isinstance(r, str)),
        entries={k: str(v) for k, v in entries.items()} if isinstance(entries, dict) else {},
        rules=tuple(r for r in raw.get("rules", []) if isinstance(r, str)),
        settings_keys=tuple(k for k in raw.get("settings_keys", []) if isinstance(k, str)),
    )


def _existing_ledger(root: Path) -> AttachLedger | None:
    """The ledger, or `None` when there is none — the one caller that may carry on without it."""
    if not (root / LEDGER).is_file():
        return None
    return ledger(root)


def _write_ignore_region(root: Path) -> None:
    """Make `.keelline/local/` untracked, or refuse.

    One `scaffold.upsert` with the `keelline:ignore` marker: everything outside the region comes
    back out as it went in, which is the whole point of a managed region and the reason this
    does not need C2's manifest.
    """
    path = root / GITIGNORE
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        raise Refusal(
            f"{GITIGNORE} cannot be read ({exc}), so `.keelline/local/` cannot be made "
            f"untracked — and writing the attach ledger into a tracked path would publish "
            f"your personal allow rules to every collaborator"
        ) from exc
    updated = upsert(text, IGNORE_REGION, "\n".join((IGNORE_NOTE, *IGNORED)), Style.HASH)
    if updated == text:
        return
    try:
        fsops.write_within(root, GITIGNORE, updated)
    except OSError as exc:
        raise Refusal(
            f"{GITIGNORE} cannot be written ({exc}), so `.keelline/local/` cannot be made "
            f"untracked — refusing rather than leaving the attach ledger in a tracked path"
        ) from exc


def _allow_list(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    permissions = raw.get("permissions", {})
    if not isinstance(permissions, dict):
        raise EntriesError(f"{LOCAL_SETTINGS}: 'permissions' is not an object")
    allow = permissions.get("allow", [])
    if not isinstance(allow, list) or not all(isinstance(rule, str) for rule in allow):
        raise EntriesError(f"{LOCAL_SETTINGS}: 'permissions.allow' is not a list of strings")
    return dict(permissions), list(allow)


def _merged_settings(document: str, diff: PermissionDiff, binding: Binding) -> str:
    """The local settings document with the overlay's rules and entries merged in.

    The allow rules are appended in order and the hook entries go through
    `scaffold.apply_entries`, which is what keys them by marker.
    """
    wanted = overlay_entries(binding)
    if not diff.added_allow and not wanted and not owned_ids(document):
        # Nothing to add, so nothing is touched. A rewrite here would reformat a file the owner
        # owns, on a run that changed nothing, and report itself as a write.
        #
        # **`owned_ids` is the third clause and not decoration.** `apply_entries(document, {})`
        # is the engine's *removal* path, and an overlay that has had its last hook entry taken
        # out reaches here with `wanted` empty — so without this the marked entry stays in the
        # file and goes on firing, while the ledger (built from the overlay, not unioned) loses
        # it. `doctor._hook_entries` then reads an entry claiming the marker and named in no
        # ledger, goes RED, and tells the owner to remove an entry Keelline installed. This is
        # the twin of the case already fixed for `rules`, answered on the settings side rather
        # than in the ledger, because the honest repair is to take the entry back out.
        return document
    raw = settings_document(document)
    permissions, allow = _allow_list(raw)
    allow += [rule for rule in diff.added_allow if rule not in allow]
    if allow or permissions:
        permissions["allow"] = allow
        raw["permissions"] = permissions
    return apply_entries(json.dumps(raw, indent=2) + "\n", wanted)


def _codex_rules(root: Path, binding: Binding) -> tuple[str, ...]:
    """Copy the overlay's standing rules to where Codex reads them (§6.3).

    Kept apart from the Claude settings merge because the two harnesses fail differently and a
    shared path would hide which. The list itself is `permissions.codex_rules`, so that
    `attach --check` reports exactly the files `attach` then writes rather than a second
    enumeration that could disagree with this one.
    """
    written: list[str] = []
    for target, source in codex_rules(binding):
        fsops.write_within(root, target, source.read_text(encoding="utf-8"))
        written.append(target)
    return tuple(written)


def _record_binding(binding: Binding) -> bool:
    """Write `projects/<name>/project.toml`, keeping the first-attach date it already carries.

    The record is the owner's consent (§6.2: "bound remote URL(s), first-attach date"), so a
    repository the overlay already records correctly is left alone — re-stamping the date on
    every attach would turn a fact into a timestamp of the last run.
    """
    if binding.state != MISMATCH and binding.recorded is not None:
        return False
    if binding.remote is None:
        raise Refusal(
            "this repository has no `origin` remote, so there is nothing for the overlay to "
            "record; add one, or bind the clone that has it"
        )
    relative = f"{PROJECTS}/{binding.project}/{PROJECT_RECORD}"
    first = _first_attach(binding.overlay / relative) or datetime.date.today().isoformat()
    # `tomlout` and not an f-string: the value is a git remote URL, which is repository-authored
    # by the Global Constraints' own list, and one carrying a quote and a newline would write
    # further keys into the record that decides what `attach` trusts.
    fsops.write_within(
        binding.overlay,
        relative,
        tomlout.dumps({"": {"remote": binding.remote, "first_attach": first}}),
    )
    return True


def _first_attach(record: Path) -> str | None:
    if not record.is_file():
        return None
    try:
        raw = tomllib.loads(record.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    value = raw.get("first_attach")
    return value if isinstance(value, str) and value else None


def _secret_scan(binding: Binding, runner: Runner) -> str | None:
    """§6.3: run `pre-commit install` in the overlay if it is missing.

    `overlay init` runs it on the machine that created the overlay, which is the first attach's
    happy path — but a second machine clones an overlay initialised elsewhere and never runs
    `init` again. Doing it twice is free; not doing it at all leaves the commit-time secret scan
    unarmed on exactly the machine that thinks it is set up. A missing `pre-commit` is a note,
    never a traceback.
    """
    if not (binding.overlay / PRE_COMMIT_CONFIG).is_file():
        return None
    try:
        installed = (hooks_dir(binding.overlay) / PRE_COMMIT_HOOK).exists()
    except Refusal:
        # `hooks_dir` shells out to `git`, and a `git` that cannot answer is this lane's own
        # kind of missing optional binary: a note, never a traceback, and never a `pre-commit
        # install` fired blind at an overlay whose hooks directory nobody could name.
        return (
            "`git` could not name the overlay's hooks directory, so whether its commit-time "
            "secret scan is installed was not checked; the push-time scan still runs"
        )
    if installed:
        return None
    done = runner.run(["pre-commit", "install"], binding.overlay)
    if done.code == 0:
        return "installed the overlay's commit-time secret scan with `pre-commit install`"
    detail = done.stderr.strip() or done.stdout.strip() or f"exit {done.code}"
    return (
        f"`pre-commit install` did not run in the overlay ({detail}), so its commit-time secret "
        f"scan is not installed; the push-time scan still runs"
    )


def _write_ledger(
    root: Path,
    binding: Binding,
    diff: PermissionDiff,
    rules: tuple[str, ...],
    settings_keys: tuple[str, ...],
) -> None:
    """Record what this attach may remove again — the union with what an earlier one claimed.

    The union is not a nicety. A second attach against an unchanged overlay has an *empty*
    diff, because every rule is already present, so a ledger written from the diff alone would
    forget what the first one added and leave `detach` nothing to remove.
    """
    previous = _existing_ledger(root)
    allow = list(previous.allow) if previous is not None else []
    allow += [rule for rule in diff.added_allow if rule not in allow]
    # The same union for the rule files, and for a sharper reason than the one above. A file
    # deleted from the overlay between two attaches is not written this time and so drops out of
    # a ledger built from this run alone — while the copy from the first attach is still sitting
    # in `.codex/rules/`, where Codex reads it as a standing instruction. `detach` would then
    # leave an agent-steering file behind, and §6.3 asks for "idempotent and reversible by
    # `detach`".
    placed = list(previous.rules) if previous is not None else []
    placed += [rule for rule in rules if rule not in placed]
    # `scaffold.marker_id` and not a second parser for the marker: the ledger's keys have to be
    # the keys `owned_ids` answers in, or `doctor`'s provenance row compares two spellings.
    # A named helper and not a walrus in the comprehension: a walrus binds in the *enclosing*
    # scope, so `(claimed := ...)` here quietly overwrote the allow list two lines above and the
    # ledger recorded a marker id as a permission rule.
    entries = {
        found: event
        for event, groups in overlay_entries(binding).items()
        for group in groups
        for entry in group["hooks"]
        for found in (marker_id(entry["command"]),)
        if found is not None
    }
    document = {
        "format": LEDGER_FORMAT,
        "store": str(binding.store),
        "allow": allow,
        "entries": entries,
        "rules": placed,
        "settings_keys": list(settings_keys),
    }
    fsops.write_within(root, LEDGER, json.dumps(document, indent=2, sort_keys=True) + "\n")


def _prepare_store(binding: Binding, config: Config) -> None:
    """Create this project's own group directories in the overlay.

    The link tree has to land on something: `memory.store` drops a group whose target does not
    exist, and a store with no groups does not resolve at all. `common/memory` is not created
    here — it is shared across projects and `overlay create` ships it.
    """
    for group in config.memory.groups:
        if group == COMMON_GROUP:
            continue
        try:
            fsops.mkdirs_within(
                binding.overlay, f"{PROJECTS}/{binding.project}/memory/{group}/{_INSIDE}"
            )
        except UnsafePath as exc:
            # The entry itself is repository-authored (§7.4: `memory.groups` reaches no guard of
            # its own), so it is refused rather than quoted back.
            raise Refusal(
                "a memory.groups entry does not stay inside this project's share of the "
                "overlay, so it is refused rather than created"
            ) from exc


def _worktrees(root: Path) -> list[Path]:
    """Every checkout of this repository, from `git worktree list --porcelain`.

    Through `gitenv.git_run`, which scrubs `GIT_DIR` and `GIT_WORK_TREE`: an inherited one would
    list the worktrees of a different repository altogether, and this lane then writes into each
    one of them.
    """
    code, out = git_run(root, "worktree", "list", "--porcelain")
    if code != 0:
        raise Failure(
            "`git` could not list this repository's worktrees, so memory cannot be linked into "
            "them; the fault is on this machine — check that `git` runs here"
        )
    prefix = "worktree "
    return [Path(line[len(prefix) :]) for line in out.splitlines() if line.startswith(prefix)]


def _link_everywhere(
    root: Path, binding: Binding, config: Config, *, machine: Path | None, home: Path | None
) -> Links:
    """The owning checkout first, then every other worktree (§6.3).

    `attach_main` handles the checkout that holds the store — the case `worktree.link` excludes
    — and `link` handles the rest unchanged. A `PartialLink` is left to propagate with its
    `.created` intact: a half-built tree is repairable, and swallowing it into a generic failure
    is what made one mysterious.
    """
    links = attach_main(root, binding.store, config, machine=machine, home=home)
    created, revoked = list(links.created), list(links.revoked)
    store = resolve(root, config, machine=machine)
    if store is None:
        raise Failure(
            "the link tree was created and the store still does not resolve; "
            "`keelline memory index --check` reports why"
        )
    owner = main_checkout(root).resolve()
    for tree in _worktrees(root):
        if tree.resolve() == owner:
            continue
        more = link(tree, store, config, home=home)
        created += more.created
        revoked += more.revoked
    return Links(created, revoked)


def _harness_fallback(
    root: Path, config: Config, *, machine: Path | None, home: Path | None
) -> tuple[str, ...]:
    """§6.3's fallback, taken only when the symlink could not be made, and always recorded.

    The link is preferred "because a settings-file value is subject to workspace trust and a
    link is not". It cannot be made on a filesystem that refuses symlinks, or where a real
    directory already sits at the path — the case `worktree._link` refuses to clobber. The gate
    is asked first and with the same predicate, so a store the owner has not approved gets
    neither channel; and the key goes into the ledger, because a fallback nothing records is a
    setting that outlives its reason.
    """
    store = resolve(root, config, machine=machine)
    if store is None or not harness_link_needed(store, config):
        return ()
    harness = harness_memory_path(root, home)
    if harness.is_symlink() and harness.readlink() == store.path.resolve():
        return ()
    document = settings_document(local_document(root))
    document[FALLBACK_KEY] = str(store.path.resolve())
    fsops.write_within(root, LOCAL_SETTINGS, json.dumps(document, indent=2) + "\n")
    return (FALLBACK_KEY,)


def attach(
    root: Path,
    *,
    store: Path,
    machine: Path | None,
    confirmed: bool,
    trust_remote: bool,
    runner: Runner,
    home: Path | None,
) -> Attached:
    """Bind this repository to the overlay, merge what the overlay grants, and link the notes in.

    The order is the order the refusals have to happen in: read the binding, which already
    refuses a store outside the machine-recorded overlay; compute the diff; refuse a widening
    without `confirmed`; refuse a mismatch without `trust_remote`; then write, `.gitignore`
    first, so the ledger is never in a tracked path even for an instant.

    The binding record is written before the links, because `memory.store` checks it and a
    store whose record is missing does not resolve — and `attach_main` resolves as its last
    step. The ledger is written before the links too, so a `PartialLink` half way through leaves
    behind a repository `detach` can still clean up.

    `runner` and `home` are keyword-**required** rather than defaulted so that no test can reach
    a real `pre-commit` or the developer's own `~/.claude/`. A default here would leave that as
    a convention, which is the thing the rule exists to replace: while this wave was being
    written, every call that omitted `home` computed a path under the real home directory.
    """
    binding = read_binding(root, store=store, machine=machine)
    diff = diff_permissions(root, binding)
    if diff.widens and not confirmed:
        raise Refusal(
            f"attaching would add {len(diff.added_allow)} allow rule(s) and "
            f"{len(diff.added_hooks)} hook entr(ies) to {LOCAL_SETTINGS}, which grants "
            f"capability. Read the diff with `keelline attach --check` and pass --yes to "
            f"confirm it"
        )
    if binding.state == MISMATCH and not trust_remote:
        raise Refusal(
            # The name is not quoted back, for the reason `permissions.check` states at length:
            # `project.name` is repository-authored and looser than the marker-id grammar
            # `doctor` already refuses to print, and a refusal built out of one is still one.
            "the overlay records a different remote under this project's name, so this is not "
            "the repository it was bound to; pass --trust-remote only if it should be"
        )
    _write_ignore_region(root)
    rules = _codex_rules(root, binding)
    document = local_document(root)
    merged = _merged_settings(document, diff, binding)
    written = merged != document
    if written:
        fsops.write_within(root, LOCAL_SETTINGS, merged)
    _write_ledger(root, binding, diff, rules, ())
    recorded = _record_binding(binding)
    config = load(root, machine=machine)
    _prepare_store(binding, config)
    links = _link_everywhere(root, binding, config, machine=machine, home=home)
    notes = [] if (note := _secret_scan(binding, runner)) is None else [note]
    keys = _harness_fallback(root, config, machine=machine, home=home)
    if keys:
        _write_ledger(root, binding, diff, rules, keys)
        notes.append(
            f"the harness memory link could not be created, so {FALLBACK_KEY} was recorded in "
            f"{LOCAL_SETTINGS} instead; `keelline detach` removes it"
        )
    return Attached(written or bool(keys), rules, recorded, True, tuple(notes), links)


@dataclass(frozen=True)
class Detached:
    """What one `detach` withdrew. The binding record is not on this list, on purpose."""

    allow_removed: tuple[str, ...]
    entries_removed: tuple[str, ...]
    rules_removed: tuple[str, ...]
    settings_keys_removed: tuple[str, ...]
    ignore_region_removed: bool
    links: Links


def _emptied(raw: dict[str, Any]) -> dict[str, Any]:
    """The settings document with the containers `detach` just emptied taken out again.

    An empty `permissions.allow` is not what the file looked like before `attach`, and the round
    trip this command promises is measured in bytes: `tests/attach/test_detach.py` snapshots
    every file under the root and compares. `apply_entries` already does the same for `hooks`.
    """
    permissions = raw.get("permissions")
    if isinstance(permissions, dict):
        if permissions.get("allow") == []:
            permissions.pop("allow")
        if not permissions:
            raw.pop("permissions")
    return raw


def _withdraw_settings(root: Path, recorded: AttachLedger) -> tuple[str, ...]:
    """Take exactly the recorded rules, the marked entries and the fallback key back out.

    The allow rules come from the ledger and never from a guess at their content: that is the
    whole reason the ledger exists. The hook entries come out through `scaffold.apply_entries`
    with nothing wanted, which is the engine's own removal path — foreign entries keep their
    matcher and their position, and a group that mixes the two is split rather than dropped.
    """
    document = local_document(root)
    if not document.strip():
        return ()
    raw = settings_document(document)
    permissions, allow = _allow_list(raw)
    removed = tuple(rule for rule in recorded.allow if rule in allow)
    if permissions:
        permissions["allow"] = [rule for rule in allow if rule not in recorded.allow]
        raw["permissions"] = permissions
    for key in recorded.settings_keys:
        raw.pop(key, None)
    remaining = json.loads(apply_entries(json.dumps(_emptied(raw), indent=2) + "\n", {}))
    if remaining:
        fsops.write_within(root, LOCAL_SETTINGS, json.dumps(remaining, indent=2) + "\n")
    else:
        # `{}` is not what the file looked like before `attach`; a file holding nothing is one
        # this command created and is the last thing it takes away.
        fsops.remove_within(root, LOCAL_SETTINGS)
    return removed


def _withdraw_ignore_region(root: Path) -> bool:
    path = root / GITIGNORE
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    remaining = drop(text, IGNORE_REGION, Style.HASH)
    if remaining == text:
        return False
    if remaining.strip():
        fsops.write_within(root, GITIGNORE, remaining)
    else:
        fsops.remove_within(root, GITIGNORE)
    return True


def detach(root: Path, *, machine: Path | None, home: Path | None) -> Detached:
    """Remove exactly what `attach` added, reading the ledger for what that was.

    It does **not** touch `projects/<name>/project.toml`. That record is the owner's consent
    (§6.2), not a piece of local state: deleting it would turn every later re-attach into a
    first attach, and re-ask a question that was already answered.

    `machine` and `home` are keyword-required for the reason every function in this wave takes
    them, and required rather than defaulted for the reason `attach` gives: a resolver without a
    machine file reads the developer's real `~/.config/keelline/`, and the harness link is under
    their real home. A caller that means "the machine owner's own" says `None` out loud.
    """
    recorded = ledger(root)
    config = load(root, machine=machine)
    entries = tuple(sorted(owned_ids(local_document(root))))
    allow_removed = _withdraw_settings(root, recorded)
    rules_removed: list[str] = []
    for rule in recorded.rules:
        if (root / rule).is_file():
            fsops.remove_within(root, rule)
            rules_removed.append(rule)
    revoked = list(detach_main(root, config, home=home).revoked)
    owner = main_checkout(root).resolve()
    for tree in _worktrees(root):
        if tree.resolve() != owner:
            revoked += detach_main(tree, config, home=home).revoked
    region = _withdraw_ignore_region(root)
    fsops.remove_within(root, LEDGER)
    return Detached(
        allow_removed,
        entries,
        tuple(rules_removed),
        recorded.settings_keys,
        region,
        Links([], revoked),
    )
