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
    CODEX_RULES,
    LOCAL_SETTINGS,
    PermissionDiff,
    codex_rules,
    diff_permissions,
    local_document,
    overlay_entries,
    settings_document,
)
from keelline.config.loader import load
from keelline.config.paths import PathEscape, contained
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
    mark,
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
# The third refusal `attach` owes before it writes anything, kept beside the other two rather
# than inside `_record_binding` where it used to live. `_record_binding` runs after the ignore
# region, the Codex rules, the settings merge and the ledger, so a checkout with no `origin`
# exited 2 having left four artifacts behind — and `doctor._attached`, which keys on the
# ledger's existence, then reported the repository attached.
NO_ORIGIN = (
    "this repository has no `origin` remote, so there is nothing for the overlay to record; "
    "add one, or bind the clone that has it"
)
# The seventh, and the one whose trigger is repository-authored (§7.4: `memory.groups` reaches no
# guard of its own). One constant for the check above every write and for the `O_NOFOLLOW` walk
# that is the floor under it, because two spellings of one refusal are two refusals to keep in
# step. The entry is never quoted back into it.
GROUP_ESCAPES = (
    "a memory.groups entry does not stay inside this project's share of the overlay, so it is "
    "refused rather than created"
)
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
    """The only witness an allow rule has (DP4), and the record `detach` acts from.

    Not *authority*, and the difference is the whole of this docstring. `.gitignore` does not
    untrack a file a clone committed, so this path can arrive in a fresh checkout with contents
    nobody on this machine wrote — and `detach` then deletes files by the strings in `rules` and
    drops settings keys by the strings in `settings_keys`. A ledger claiming
    `settings_keys = ["permissions"]` deleted the owner's whole `permissions` block, **deny rules
    included**: a widening driven by repository-authored bytes, out of a file this module used to
    call an authority.

    So `ledger()` answers one question about every field before `detach` sees it — *what could
    `attach` possibly have written here?* — and refuses anything outside that answer rather than
    obeying it. The two fields that name things to destroy are bounded exactly:

    - `rules` may only be `.codex/rules/<file>`, the one place `permissions.codex_rules`
      enumerates, one path segment deep and never a dotfile; and
    - `settings_keys` may only be `autoMemoryDirectory`, the one key `_harness_fallback` writes.

    `entries` keys must parse as marker ids, because `_write_ledger` builds them with
    `scaffold.marker_id` and nothing else can appear there.

    `allow` and `store` are not bounded here, and saying why is part of the rule rather than an
    omission. An allow rule has no grammar this lane owns — the ledger exists *because* a rule
    cannot be told from the owner's own by its content — and `_withdraw_settings` only ever
    removes a rule the settings file already holds, so the worst a committed `allow` achieves is
    taking a permission away. `store` reaches `read_binding`, which refuses any path that is not
    this project's own share of the recorded overlay.

    `entries` maps each marker id to its event, which is the shape `scaffold.owned_ids` answers
    in, so `doctor` can compare the two without a translation in between.
    """

    store: str
    allow: tuple[str, ...]
    entries: dict[str, str]
    rules: tuple[str, ...]
    settings_keys: tuple[str, ...]


def _rule_is_writable(rule: str) -> bool:
    """Whether `attach` could have written this path: `.codex/rules/<file>` and nothing else.

    `permissions.codex_rules` composes every target as `f"{CODEX_RULES}/{rule.name}"` over a
    directory listing, so the answer is one path segment under that prefix, never a dotfile and
    never a nested path. `.github/workflows/ci.yml` and `src/keelline/__init__.py` are all
    inside the root `fsops.remove_within` contains the removal to, which is why containment is
    not the guard that matters here.
    """
    prefix = f"{CODEX_RULES}/"
    if not rule.startswith(prefix):
        return False
    name = rule[len(prefix) :]
    return bool(name) and "/" not in name and not name.startswith(".")


def _checked(raw: dict[str, Any], path: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`rules` and `settings_keys`, or a `Refusal` counting the members `attach` never wrote.

    Counted and never quoted: these strings are repository-authored by the Global Constraints'
    own list, and a refusal built out of one is still one.
    """
    rules = tuple(r for r in raw.get("rules", []) if isinstance(r, str))
    keys = tuple(k for k in raw.get("settings_keys", []) if isinstance(k, str))
    foreign = sum(1 for rule in rules if not _rule_is_writable(rule))
    foreign += sum(1 for key in keys if key != FALLBACK_KEY)
    if foreign:
        raise Refusal(
            f"{path} names {foreign} file(s) or settings key(s) that `keelline attach` could "
            f"never have written, so it is not a record of an attach on this machine; nothing "
            f"was removed. Delete it, or take it out of the clone that committed it"
        )
    return rules, keys


def ledger(root: Path) -> AttachLedger:
    """The ledger this repository's last `attach` wrote, or a `Failure` naming the missing file.

    Never a best effort. Guessing which allow rules were Keelline's from their content is the
    heuristic this file exists to replace, and a `detach` built on a guess removes a rule the
    owner wrote by hand — which is worse than removing none.

    A ledger whose `rules` or `settings_keys` name something `attach` could not have written is
    a `Refusal` rather than a filtered list: see `AttachLedger`. Filtering would let a committed
    ledger keep the members it is entitled to and lose only the hostile ones, which is a partial
    defence reported as a success.
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
    rules, keys = _checked(raw, path)
    entries = raw.get("entries")
    return AttachLedger(
        store=str(raw.get("store", "")),
        allow=tuple(r for r in raw.get("allow", []) if isinstance(r, str)),
        entries=(
            # `mark`/`marker_id` and not a second copy of the marker grammar: `_write_ledger`
            # builds these keys with `marker_id`, so a key that does not round-trip through the
            # engine's own pair is one no attach could have recorded. Dropped rather than
            # refused, because a key names nothing to destroy: what it costs is a provenance
            # row, and `doctor` reporting an entry as unrecorded is the conservative answer.
            {k: str(v) for k, v in entries.items() if marker_id(mark("", k)) == k}
            if isinstance(entries, dict)
            else {}
        ),
        rules=rules,
        settings_keys=keys,
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
        # The floor under `attach`'s own hoisted copy, never the first place this is asked. A
        # `Refusal` reaching here means the hoist above drifted — and by then the ignore region,
        # `.codex/rules/`, the settings merge and the ledger have all been written, which is
        # exactly the state the hoist exists to prevent.
        raise Refusal(NO_ORIGIN)
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
    previous: AttachLedger | None,
) -> None:
    """Record what this attach may remove again — the union with what an earlier one claimed.

    The union is not a nicety. A second attach against an unchanged overlay has an *empty*
    diff, because every rule is already present, so a ledger written from the diff alone would
    forget what the first one added and leave `detach` nothing to remove.

    **`previous` is handed in and not read here**, which is a refusal's position and not a
    refactor. This function used to call `_existing_ledger` itself, and `ledger()` refuses a
    ledger naming files or settings keys `attach` could not have written — so that refusal fired
    from the fourth write of the run, with the ignore region, the `.codex/rules/` copies and the
    settings merge already on disk and the committed ledger still there for `doctor._attached`
    to read as "attached". That is the shape `attach`'s own docstring says all its refusals must
    not have. The caller reads it once, above every write.

    Reading it once is also the more correct union: `attach` writes the ledger twice in a run,
    and the second call would otherwise union against the file the first call just wrote.
    """
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


def _group_directories(binding: Binding, config: Config) -> list[str]:
    """Every directory this project's groups need inside the overlay, as one spelling.

    One list for the check and for the write both, so the refusal above every write and the
    `O_NOFOLLOW` walk that does the writing cannot come to disagree about which paths they are
    talking about. `common/memory` is not here — it is shared across projects and `overlay
    create` ships it — and skipping it in one of the two would be the first way they drift.
    """
    return [
        f"{PROJECTS}/{binding.project}/memory/{group}/{_INSIDE}"
        for group in config.memory.groups
        if group != COMMON_GROUP
    ]


def _check_groups(binding: Binding, config: Config) -> None:
    """Refuse a `memory.groups` entry that leaves this project's share of the overlay — first.

    §7.4 and D15: `memory.groups` is repository-authored and reaches no guard of its own —
    `config/paths.py` says so in as many words, and names this lane as the one that has to call
    the containment itself. This lane was calling it, and calling it too late: the refusal came
    out of `_prepare_store`, which runs after the ignore region, the `.codex/rules/` copies, the
    settings merge, the ledger **and** the overlay's binding record. So a clone committing
    `groups = ["../../escape"]` got `attach` to write five artifacts and exit 2, with
    `doctor._attached` — which keys on the ledger existing — then reporting the repository
    attached and the binding *bound*, because the record had been written too.

    Hoisting it here is not only a reordering: it is this project's own two-stage rule, which
    `attach` was skipping for this one path. `config.paths.contained` "decides whether a
    configured path *may* be written — it gives a user-facing refusal and catches a committed
    symlink", and `fsops.mkdirs_within` then does the write through an `O_NOFOLLOW` walk so a
    component that becomes a symlink *after* the check cannot redirect it. `attach` had only the
    second half, which is why its user-facing refusal arrived at write time.

    `resolved_root` is passed because this validates many paths against one root, which is the
    parameter's documented reason for existing.
    """
    resolved = binding.overlay.resolve()
    for relative in _group_directories(binding, config):
        try:
            contained(binding.overlay, relative, resolved_root=resolved)
        except PathEscape as exc:
            # The entry itself is repository-authored, so it is refused rather than quoted back.
            raise Refusal(GROUP_ESCAPES) from exc


def _prepare_store(binding: Binding, config: Config) -> None:
    """Create this project's own group directories in the overlay.

    The link tree has to land on something: `memory.store` drops a group whose target does not
    exist, and a store with no groups does not resolve at all.

    **The `UnsafePath` arm is the floor under `_check_groups` and is not dead.** A spelling that
    escapes was already refused above every write, so that half reaching here means the hoist
    drifted. The other half cannot be hoisted and should not be: `contained` asks the filesystem
    a question and this walk asks it again at the moment of writing, so a component of the
    overlay that became a symlink in between refuses here and nowhere earlier. That is the
    interval the `O_NOFOLLOW` walk exists for, and it is the one remaining way this refusal can
    arrive after a write.
    """
    for relative in _group_directories(binding, config):
        try:
            fsops.mkdirs_within(binding.overlay, relative)
        except UnsafePath as exc:
            raise Refusal(GROUP_ESCAPES) from exc


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

    **`attach_main` is applied to the owning checkout and never to `--root`.** It used to be
    applied to whatever `--root` named, and the loop below then skipped `main_checkout(root)`
    unconditionally — so `keelline attach` run from a linked worktree built that worktree's tree
    twice and the main checkout's not at all. `worktree.link` is documented as a no-op for the
    main checkout, so nothing downstream would have caught it: every session in the owning
    checkout saw no memory, silently, and the command exited 0. The code already computed
    `owner`; it simply handed the owning-checkout entry point the wrong root.

    The skip is by resolved path and accumulates, so `root` — which `_worktrees` lists like any
    other — is linked exactly once whether or not it is the owner.
    """
    owner = main_checkout(root).resolve()
    links = attach_main(owner, binding.store, config, machine=machine, home=home)
    created, revoked = list(links.created), list(links.revoked)
    # Resolved against the owner and not against `root`: in overlay mode `resolve` reads the
    # link tree, and the tree that exists at this point is the one `attach_main` just built.
    store = resolve(owner, config, machine=machine)
    if store is None:
        raise Failure(
            "the link tree was created and the store still does not resolve; "
            "`keelline memory index --check` reports why"
        )
    linked = {owner}
    for tree in _worktrees(root):
        if tree.resolve() in linked:
            continue
        linked.add(tree.resolve())
        more = link(tree, store, config, home=home)
        created += more.created
        revoked += more.revoked
    return Links(created, revoked)


def _recorded_keys(root: Path) -> tuple[str, ...]:
    """The settings keys `attach` owns that `.claude/settings.local.json` holds *right now*.

    Read back from the file rather than carried out of the run that wrote it, because
    `settings_keys` is a claim about state that persists. `_write_ledger` used to be handed `()`
    on every run and the fallback's own return value only when it had just written the key — so
    the second attach after a fallback reset the record to `[]` while the key was still in the
    file, and `detach` then left it there for good.
    """
    return (FALLBACK_KEY,) if FALLBACK_KEY in settings_document(local_document(root)) else ()


def _harness_fallback(
    root: Path, config: Config, *, machine: Path | None, home: Path | None
) -> tuple[str, ...]:
    """§6.3's fallback, taken only when the symlink could not be made — and withdrawn again here.

    The link is preferred "because a settings-file value is subject to workspace trust and a
    link is not". It cannot be made on a filesystem that refuses symlinks, or where a real
    directory already sits at the path — the case `worktree._link` refuses to clobber. The gate
    is asked with the same predicate `worktree.harness_link_needed` answers for the link itself,
    so a store the owner has not approved gets neither channel.

    **And it is asked in both directions, in the same call**, which is `memory/worktree`'s rule
    one hop over: "a gate evaluated once, at creation, over state that persists is not a gate".
    A settings value is exactly such state, and this is the same channel that module calls "the
    one hop that leaves this lane's gate" — the harness's own native reader, outside every
    delimiter and every trust record this lane controls. `_apply_harness_link` already revokes
    the *symlink* when the record lapses; this key outlived it, so a `git pull` that added one
    note shut every channel except the one pointing the harness straight at the new bytes.

    The two arms that return without writing are the two that used to leak: the link is no
    longer needed, and the symlink now exists so the fallback is no longer warranted. Both now
    take the key back out. The answer is what the file holds afterwards, so the caller's ledger
    is the file's own state rather than a memory of this run.

    **This is the one place `attach` removes a file**, and it is worth saying out loud rather
    than leaving to be discovered. Withdrawing the key can empty `.claude/settings.local.json`,
    and `{}` is not what that file looked like before the fallback was taken — it is a file
    `attach` created and this is the last thing it takes away, which is the rule
    `_withdraw_settings` already applies on the `detach` side and what keeps the round trip
    byte-for-byte. It can only fire when Keelline's own key was all the file held, so nothing of
    the owner's is ever what goes.
    """
    store = resolve(root, config, machine=machine)
    wanted: str | None = None
    if store is not None and harness_link_needed(store, config):
        harness = harness_memory_path(root, home)
        if not (harness.is_symlink() and harness.readlink() == store.path.resolve()):
            wanted = str(store.path.resolve())
    document = settings_document(local_document(root))
    if document.get(FALLBACK_KEY) == wanted:
        # Includes the ordinary case where the key is absent and is not wanted: nothing to do,
        # and rewriting a file the owner owns on a run that changed nothing is a write.
        return _recorded_keys(root)
    if wanted is None:
        document.pop(FALLBACK_KEY, None)
    else:
        document[FALLBACK_KEY] = wanted
    if document:
        fsops.write_within(root, LOCAL_SETTINGS, json.dumps(document, indent=2) + "\n")
    else:
        # `{}` is not what the file looked like before the fallback was taken, and a document
        # holding only this key is one `attach` created — the same rule `_withdraw_settings`
        # applies when `detach` empties it.
        fsops.remove_within(root, LOCAL_SETTINGS)
    return () if wanted is None else (FALLBACK_KEY,)


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
    without `confirmed`; refuse a mismatch without `trust_remote`; refuse a checkout with no
    `origin`; read the existing ledger, which refuses one no attach could have written; refuse a
    `memory.groups` entry that leaves this project's share of the overlay; then write,
    `.gitignore` first, so the ledger is never in a tracked path even for an instant.

    **All six refusals are above every write, and three of them were not.** The no-`origin` one
    lived in `_record_binding`, the ledger's in `_write_ledger`, and the `memory.groups` one in
    `_prepare_store` — which runs after the ignore region, the Codex rule files, the settings
    merge, the ledger *and* the overlay's binding record. Each could exit 2 having written three,
    four or five artifacts, with `doctor._attached` — which keys on the ledger existing — then
    reporting the repository attached, and in the third case *bound*, because the record had been
    written too. A refusal that leaves a repository looking attached is not a refusal. The second
    of the three arrived in the commit that wrote that sentence down, and the third was found by
    asking whether the shape was dead or only its named instances were.

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
    if binding.remote is None:
        raise Refusal(NO_ORIGIN)
    # The sixth refusal, and it belongs here for the reason the five above it do. `ledger()`
    # refuses a ledger naming files or settings keys `attach` could not have written, and
    # `_write_ledger` used to ask for it — from the fourth write of the run. A clone that
    # commits such a ledger could therefore make `attach` write the ignore region, copy
    # `.codex/rules/*` and merge `.claude/settings.local.json` before exiting 2, with the
    # committed ledger still on disk for `doctor._attached` to read as "attached", and with
    # `attach --check` reporting clean beforehand because it does not read the ledger at all.
    # Loaded here rather than after the binding record, which is where it used to be: the
    # `memory.groups` refusal below needs the configuration, and a check cannot happen above the
    # writes while what it reads is loaded below them.
    config = load(root, machine=machine)
    _check_groups(binding, config)
    previous = _existing_ledger(root)
    _write_ignore_region(root)
    rules = _codex_rules(root, binding)
    document = local_document(root)
    merged = _merged_settings(document, diff, binding)
    written = merged != document
    if written:
        fsops.write_within(root, LOCAL_SETTINGS, merged)
    # What an earlier attach left in the settings file, carried into the ledger written before
    # the links so that a `PartialLink` half way through still leaves `detach` able to remove
    # it. The real answer is taken again below, after the only function that can change it.
    carried = _recorded_keys(root)
    _write_ledger(root, binding, diff, rules, carried, previous)
    recorded = _record_binding(binding)
    _prepare_store(binding, config)
    links = _link_everywhere(root, binding, config, machine=machine, home=home)
    notes = [] if (note := _secret_scan(binding, runner)) is None else [note]
    keys = _harness_fallback(root, config, machine=machine, home=home)
    if keys != carried:
        _write_ledger(root, binding, diff, rules, keys, previous)
        written = True
    if keys:
        notes.append(
            f"the harness memory link could not be created, so {FALLBACK_KEY} was recorded in "
            f"{LOCAL_SETTINGS} instead; `keelline detach` removes it"
        )
    return Attached(written, rules, recorded, True, tuple(notes), links)


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

    **It needs the ledger in the checkout it is run from, and that is a limitation rather than a
    defect.** `.keelline/local/` is untracked and per-checkout, so a sibling worktree does not
    carry the ledger of the checkout an attach was run from and `detach --root <that worktree>`
    answers "no ledger". Without one there is nothing to reverse — guessing which allow rules
    were Keelline's from their content is the heuristic the ledger exists to replace. So the
    reach this function has *once it starts* is every checkout (`_worktrees` below), and the
    place it may be started from is the one that holds the record.
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
    # The mirror of `_link_everywhere`, and it had the mirror defect: `detach_main` was applied
    # to `--root` and the loop then skipped the owning checkout unconditionally, so a detach run
    # from a linked worktree withdrew that worktree's tree twice and left the main checkout's
    # link tree — and its harness link — in place. Every checkout is visited exactly once, by
    # resolved path, starting with the one that owns the store.
    owner = main_checkout(root).resolve()
    revoked = list(detach_main(owner, config, machine=machine, home=home).revoked)
    visited = {owner}
    for tree in _worktrees(root):
        if tree.resolve() in visited:
            continue
        visited.add(tree.resolve())
        revoked += detach_main(tree, config, machine=machine, home=home).revoked
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
