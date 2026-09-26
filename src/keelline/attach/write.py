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
from keelline.attach.binding import MISMATCH, Binding, read_binding, unlinked_groups
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
    PartialLink,
    attach_main,
    detach_main,
    harness_anchor,
    harness_link_needed,
    harness_memory_path,
    link,
    main_checkout,
    resolve,
)
from keelline.runner import Runner
from keelline.scaffold import (
    EntriesError,
    Manifest,
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
# Both paths the ignore region keeps out of git: the ledger's directory, and the inventory
# `keelline assess` writes.
IGNORED = (".keelline/local/", ".keelline/assessment.json")
IGNORE_NOTE = "# Keelline's local state: yours, never a collaborator's."
# The region body, spelled once. `init` (wave 4, the `project` area) records this same region
# as a scaffold artifact, and a second spelling would let `init` and `attach` each report the
# other's region as hand-edited.
IGNORE_BODY = "\n".join((IGNORE_NOTE, *IGNORED))
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
# The sixth, and the first of the two whose trigger is repository-authored (§7.4:
# `memory.groups` reaches no guard of its own). One constant for the check above every write
# and for the `O_NOFOLLOW` walk that is the floor under it, because two spellings of one
# refusal are two refusals to keep in step. The entry is never quoted back into it.
GROUP_ESCAPES = (
    "a memory.groups entry does not stay inside this project's share of the overlay, so it is "
    "refused rather than created"
)
# The eighth, and the second of the two whose trigger is repository-authored. Its anchor is
# `root` -- the checkout the command was pointed at, never a value the repository chose -- so a
# repository cannot move the directory this count is taken under: `unlinked_groups` contains
# every `<paths.memory>/<group>` against that root and refuses the ones that leave it. The
# count prints and the entries do not, for the reason `GROUP_ESCAPES` gives; the remedy names
# the shape of the destination rather than any group's name.
REAL_DIRECTORIES = (
    "{count} of this project's memory groups are real directories under paths.memory, and "
    "`attach` links rather than moves; move each into "
    "`<overlay>/projects/<the name in keelline.toml>/memory/<group>` (`common/memory` for the "
    "shared group) and run again -- `keelline attach --check` reports the count"
)
# `fsops.mkdirs_within` creates a target's *parents*, so a directory is asked for as the parent
# of a name inside it. Nothing is ever written at this name; `overlay.create` asks the same way.
_INSIDE = ".keep"
# Every directory `attach` can bring into existence in the project root, as a *closed* list,
# deepest first — which is also the order `detach` has to remove them in.
#
# There are exactly three writes that create a directory here, and each one's parents are on
# this list: `LEDGER` under `.keelline/local/`, the rule copies under `.codex/rules/`, and
# `LOCAL_SETTINGS` under `.claude/`. The link tree's directory (`paths.memory`, wherever the
# project configures it) is deliberately **not** here: it is repository-configured, may be a
# directory the project already keeps for its own reasons, and `worktree.detach_main` settled
# that question the other way — "withdrawing a link is not licence to delete a directory".
#
# Closed because a ledger is a file a clone can commit. `detach` iterates this tuple and keeps
# only the members the ledger names, so the ledger can shorten the list and never extend it,
# and a committed `["src"]` names nothing this loop will act on. `ledger()` refuses one anyway,
# on the same standard `rules` and `settings_keys` are held to.
CREATED_DIRS = (".keelline/local", ".keelline", ".codex/rules", ".codex", ".claude")


@dataclass(frozen=True)
class Attached:
    """What one `attach` changed.

    Nothing here is repository-authored. `notes` is the one field that carries text from
    outside this process -- what `pre-commit install` printed -- and that is this machine's
    tool answering in the overlay, not the clone's bytes.
    """

    settings_written: bool
    rules_written: tuple[str, ...]
    binding_recorded: bool
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

    `directories` is the third, and is bounded by membership in `CREATED_DIRS`. It records which
    of those directories this repository did **not** have before the attach, so `detach` can put
    the tree back as it found it; `rmdir` is the only removal it drives, so a directory holding
    anything at all survives regardless of what the ledger claims.

    `entries` keys must parse as marker ids, because `_write_ledger` builds them with
    `scaffold.marker_id` and nothing else can appear there.

    `allow` and `store` are not bounded here, and saying why is part of the rule rather than an
    omission. An allow rule has no grammar this lane owns — the ledger exists *because* a rule
    cannot be told from the owner's own by its content — and `_withdraw_settings` only ever
    removes a rule the settings file already holds, so the worst a committed `allow` achieves is
    taking a permission away. `store` is read by nothing: `detach` derives every path it
    withdraws from the configuration and the overlay root, never from this field, so it is a
    record for a human reading the file and for `doctor`, and a committed value costs nothing.

    `entries` maps each marker id to its event, which is the shape `scaffold.owned_ids` answers
    in, so `doctor` can compare the two without a translation in between.
    """

    store: str
    allow: tuple[str, ...]
    entries: dict[str, str]
    rules: tuple[str, ...]
    settings_keys: tuple[str, ...]
    directories: tuple[str, ...] = ()


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


def _checked(
    raw: dict[str, Any], path: Path
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """`rules`, `settings_keys` and `directories`, or a `Refusal` counting what was never written.

    Counted and never quoted: these strings are repository-authored by the Global Constraints'
    own list, and a refusal built out of one is still one.
    """
    rules = tuple(r for r in raw.get("rules", []) if isinstance(r, str))
    keys = tuple(k for k in raw.get("settings_keys", []) if isinstance(k, str))
    # Held to the same standard as the two above rather than merely filtered at the removal
    # site, so the answer to "is this a record of an attach on this machine?" is one answer.
    # `detach` also intersects with `CREATED_DIRS` when it walks them, which is the floor under
    # this; a name outside the list is a ledger no attach wrote, and that is a refusal.
    directories = tuple(d for d in raw.get("directories", []) if isinstance(d, str))
    foreign = sum(1 for rule in rules if not _rule_is_writable(rule))
    foreign += sum(1 for key in keys if key != FALLBACK_KEY)
    foreign += sum(1 for name in directories if name not in CREATED_DIRS)
    if foreign:
        raise Refusal(
            f"{path} names {foreign} file(s), settings key(s) or directory(ies) that "
            f"`keelline attach` could never have written, so it is not a record of an attach on "
            f"this machine; nothing "
            f"was removed. Delete it, or take it out of the clone that committed it"
        )
    return rules, keys, directories


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
    except UnicodeDecodeError:
        raise Failure(f"{path} is not UTF-8 text") from None
    except json.JSONDecodeError as exc:
        raise Failure(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise Failure(f"{path} is not a JSON object")
    rules, keys, directories = _checked(raw, path)
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
        directories=directories,
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
    except UnicodeDecodeError:
        raise Refusal(
            f"{GITIGNORE} is not UTF-8 text, so `.keelline/local/` cannot be made untracked — and "
            f"writing the attach ledger into a tracked path would publish your personal allow "
            f"rules to every collaborator"
        ) from None
    except OSError as exc:
        raise Refusal(
            f"{GITIGNORE} cannot be read ({exc}), so `.keelline/local/` cannot be made "
            f"untracked — and writing the attach ledger into a tracked path would publish "
            f"your personal allow rules to every collaborator"
        ) from exc
    updated = upsert(text, IGNORE_REGION, IGNORE_BODY, Style.HASH)
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
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # The overlay is the owner's, so its path may print.
            raise Failure(f"{source} is not UTF-8 text, so it was not copied") from None
        fsops.write_within(root, target, text)
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
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
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


def _absent_directories(root: Path) -> tuple[str, ...]:
    """Which of `CREATED_DIRS` this repository does not have, asked before the first write.

    Asked *before*, because after the ledger is written `.keelline/local/` exists and the answer
    is no longer the one `detach` needs. `attach` therefore takes it at the top of the run and
    hands it down, the same way it hands down `previous`.

    `is_dir()` and not `exists()`: a path of this name that is a file, or a symlink to one, is
    not a directory this run created and `rmdir` would refuse it anyway — recording it would
    only put a name in the ledger that nothing can act on.
    """
    return tuple(name for name in CREATED_DIRS if not (root / name).is_dir())


def _write_ledger(
    root: Path,
    binding: Binding,
    diff: PermissionDiff,
    rules: tuple[str, ...],
    settings_keys: tuple[str, ...],
    previous: AttachLedger | None,
    directories: tuple[str, ...],
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
    # The same union as `allow` and `rules`, for the same reason sharpened once more: the second
    # attach in a repository finds every one of these directories already there and would record
    # none, so a ledger built from this run alone would leave `detach` unable to remove what the
    # first attach created. Ordered by `CREATED_DIRS` rather than by either input, so the written
    # list is deepest-first whatever order it was unioned in.
    made = set(previous.directories if previous is not None else ()) | set(directories)
    document = {
        "format": LEDGER_FORMAT,
        "store": str(binding.store),
        "allow": allow,
        "entries": entries,
        "rules": placed,
        "settings_keys": list(settings_keys),
        "directories": [name for name in CREATED_DIRS if name in made],
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
    # One record per blank-line-separated block. A block carrying `prunable` names a worktree
    # whose directory is gone and which nobody has `git worktree prune`d yet -- the state a
    # deleted worktree is left in by the ordinary `rm -rf`. `link()` run with `cwd=<gone>`
    # raised `GitUnavailable` ("check that `git` runs here") after the ledger, the region and
    # the owner's links were written, on a machine whose `git` was fine; and `detach` in the
    # same state completed. Skipped here, so both halves read the same set.
    found: list[Path] = []
    for block in out.split("\n\n"):
        lines = block.splitlines()
        if any(line == "prunable" or line.startswith("prunable ") for line in lines):
            continue
        found.extend(
            Path(line[len("worktree ") :]) for line in lines if line.startswith("worktree ")
        )
    return found


def _checkouts(root: Path) -> list[Path]:
    """Every checkout of this repository, the one that owns the store first, each exactly once.

    Both halves need `git` — `main_checkout` asks it which checkout owns this worktree, and
    `_worktrees` asks it for the rest — which is the whole reason this is a function rather than
    four lines in each caller. `detach` calls it **before its first withdrawal** for that reason:
    a `git` that cannot run is a fact about the machine, knowable at the start, and asking it
    after the settings file and the `.codex/rules/` copies were already taken away left the
    repository half-detached over something nothing had yet touched.

    Owner first because `attach` has to build the owning checkout's tree before `resolve()` can
    answer, and `detach` mirrors the order so the two read the same way. Deduplicated by resolved
    path, so `--root` is visited exactly once whether or not it is the owner.
    """
    owner = main_checkout(root).resolve()
    found = [owner]
    seen = {owner}
    for tree in _worktrees(root):
        resolved = tree.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        found.append(resolved)
    return found


def _link_everywhere(
    root: Path, binding: Binding, config: Config, *, machine: Path | None, home: Path | None
) -> Links:
    """The owning checkout first, then every other worktree (§6.3).

    `attach_main` handles the checkout that holds the store — the case `worktree.link` excludes
    — and `link` handles the rest unchanged. A `PartialLink` propagates carrying **everything
    this run made**, across every call: a half-built tree is repairable, and swallowing it into
    a generic failure is what made one mysterious.

    That accumulation is the whole of the re-raise below. `link` builds its own `.created` per
    call, so an exception let out untouched carries the failing checkout's links and not the
    owning checkout's — which are on disk, made by `attach_main` one call earlier. This
    docstring claimed "`.created` intact" while that was false, and a list missing the links
    that were actually made defeats the type: a caller repairing from it is told nothing was
    made. `attach_main` itself is the first call, so its own `.created` is already the whole of
    what this run made and needs no wrapping.

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
    checkouts = _checkouts(root)
    owner = checkouts[0]
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
    for tree in checkouts[1:]:
        try:
            more = link(tree, store, config, home=home)
        except PartialLink as partial:
            raise PartialLink([*created, *partial.created], partial) from partial
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

    The order below is the order they are enumerated in: read the binding, which already
    refuses a store outside the machine-recorded overlay; compute the diff; refuse a widening
    without `confirmed`; refuse a mismatch without `trust_remote`; refuse a checkout with no
    `origin`; read the existing ledger, which refuses one no attach could have written; refuse a
    `memory.groups` entry that leaves this project's share of the overlay; refuse a harness
    anchor this machine cannot vouch for; refuse a group that never moved into the overlay;
    then write, `.gitignore` first, so the ledger is never in a tracked path even for an
    instant.

    The ordinals in the body number that enumeration and not the line order, and two of them
    fire out of it: the ledger's refusal is read a few lines below the two that need the
    `Config`, and the never-moved check is asked **before** the harness anchor rather than
    after it. The reason is the `Config`: `_check_groups` has just loaded it, and the
    never-moved check reads the same `memory.groups` and the same `paths.memory` — so the two
    containments over one repository-authored list stay in one place, and the anchor, which
    needs neither, follows. Nothing writes between them; every one of the eight is above the
    first write, which is the property that matters and the one the tests assert.

    **A ninth refusal is above every write and is not one of the eight**, because it is not a
    check this function makes: `unlinked_groups` contains each `<paths.memory>/<group>` against
    `root` before it counts, and a `PathEscape` out of it propagates as the refusal it already
    is — `paths.memory` may itself be a symlink, and then every group escapes at once. It is
    enumerated nowhere because it has no ordinal of its own; it is named here so that the count
    above reads as "eight checks" rather than as "eight ways this can refuse".

    **All eight checks are above every write, and three of them were not.** The no-`origin` one
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
    # One load for the whole run, handed to `read_binding` rather than left for it to make a
    # second of. `permissions.check` took this ruling for `--check` -- "two loads could
    # disagree, and a `--check` whose two halves read different documents is exactly what it
    # exists to rule out" -- and the writing command has the stronger version of that argument:
    # a `--check` that read two documents reports the wrong thing, while an `attach` that reads
    # two writes under the wrong one. `read_binding` loads on the line it is called from, so
    # nothing moves in the order the refusals happen in; what changes is that `project.name`,
    # `memory.groups` and `paths.memory` are read once and the refusals below are about the
    # same document the binding was read under.
    config = load(root, machine=machine)
    binding = read_binding(root, store=store, machine=machine, config=config)
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
    # The `Config` the two checks below read is loaded at the top of this function, which is
    # where the binding needs it anyway; it used to be loaded here, and before that after the
    # binding record, where a check could not happen above the writes while what it reads was
    # loaded below them.
    _check_groups(binding, config)
    # The eighth, and the one whose remedy is an act no command performs: `attach` **links**,
    # so a group that is still a real directory under `paths.memory` has its notes in the
    # repository and its share of the overlay empty, and linking over it would leave every
    # session reading the repository's copy with the binding record, the settings merge and
    # the ledger already written. Above every write for that reason, and beside the
    # `memory.groups` containment because it reads the same repository-authored list -- the
    # anchor it is contained against is `root`, the checkout this command was pointed at,
    # which is why a repository cannot move the directory the count is taken under. A
    # `PathEscape` out of `unlinked_groups` propagates as the refusal it already is.
    real = unlinked_groups(root, config)
    if real:
        raise Refusal(REAL_DIRECTORIES.format(count=len(real)))
    # The seventh, and the one that is not about this repository at all: the anchor for the
    # harness memory link. `_apply_harness_link` asks it per checkout, which is one frame
    # below every write here — so a home directory that is not there, and the ordinary
    # dotfiles layout that links `~/.claude` elsewhere, were discovered after the ignore
    # region, the rule files, the settings merge, the ledger and the binding record. Measured:
    # `PartialLink` with three links made, then a `detach` that could not undo it.
    #
    # Asked for `root` and not for every checkout, because `_checkouts` needs `git` and is
    # read below: every checkout shares `.claude/projects` under one home, which is the
    # component a dotfiles manager links, so the layout that reaches production is refused
    # here for all of them. A `<slug>` component that is itself a symlink is left to the
    # per-call floor in `harness_anchor`, which is a `Refusal` either way.
    harness_anchor(root, home)
    previous = _existing_ledger(root)
    # Above every write, because the first of them creates `.keelline/local/` and the answer
    # would then be wrong by exactly the directory this run brought into existence.
    absent = _absent_directories(root)
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
    _write_ledger(root, binding, diff, rules, carried, previous, absent)
    recorded = _record_binding(binding)
    _prepare_store(binding, config)
    links = _link_everywhere(root, binding, config, machine=machine, home=home)
    notes = [] if (note := _secret_scan(binding, runner)) is None else [note]
    keys = _harness_fallback(root, config, machine=machine, home=home)
    if keys != carried:
        _write_ledger(root, binding, diff, rules, keys, previous, absent)
        written = True
    if keys:
        notes.append(
            f"the harness memory link could not be created, so {FALLBACK_KEY} was recorded in "
            f"{LOCAL_SETTINGS} instead; `keelline detach` removes it"
        )
    return Attached(written, rules, recorded, tuple(notes), links)


@dataclass(frozen=True)
class Detached:
    """What one `detach` withdrew. The binding record is not on this list, on purpose."""

    allow_removed: tuple[str, ...]
    entries_removed: tuple[str, ...]
    rules_removed: tuple[str, ...]
    settings_keys_removed: tuple[str, ...]
    ignore_region_removed: bool
    links: Links
    directories_removed: tuple[str, ...] = ()


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


def _ignore_region_remainder(root: Path) -> str | None:
    """What `.gitignore` will hold once the attach region is dropped; `None` when nothing is
    there to drop.

    Asked **before the first withdrawal**, for the reason `_checkouts` is: `drop()` refuses a
    region that is opened or closed twice -- which a merge that kept both sides produces -- and
    asked where the write used to happen, that refusal came after the settings, the rule files
    and every link tree were gone, with the ledger still present. `doctor` then reported the
    repository attached, and a second `detach` failed at the same line. A region that cannot be
    withdrawn is knowable at the start, and so is a file that cannot be read.
    """
    path = root / GITIGNORE
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Failure(f"{GITIGNORE} cannot be read: {exc}") from exc
    except UnicodeDecodeError:
        raise Failure(f"{GITIGNORE} is not UTF-8 text") from None
    remaining = drop(text, IGNORE_REGION, Style.HASH)
    return None if remaining == text else remaining


def _footprint_owns_region(root: Path) -> bool:
    """Whether `keelline init`'s footprint, and not this attach, put the ignore region there.

    DC4, and it is an ownership rule rather than a last-writer one. `init` records the same
    `keelline:ignore` block as a scaffold artifact, with the body imported from this module
    rather than respelled -- a second spelling would let each command report the other's region
    as hand-edited -- and that block is **committed**. Withdrawing it would take a line out of a
    tracked file this command never wrote, and leave `upgrade` reading the footprint as
    hand-edited on a repository nobody edited. `attach`'s own write stays and is idempotent;
    only the withdrawal asks this.

    The manifest and not a new ledger field: the ledger is untracked and per-checkout, while
    "whose region is this" has to answer the same for every clone of the project. A repository
    with no manifest is one no `init` has set up -- the state every attach before `init` shipped
    leaves behind -- and its region is withdrawn exactly as it always was.

    **A manifest this cannot read answers "not mine", and that is the whole of the ruling.**
    `.keelline/manifest.json` is **tracked** -- `IGNORE_BODY` covers `.keelline/local/` and
    `.keelline/assessment.json` and nothing else -- so a clone commits it, and `Manifest.read`
    raises `ManifestError` for one that is unreadable, is not a JSON object, or declares a
    `format` past this Keelline's -- and `PathEscape` for one committed as a symlink out of the
    root. `attach` never reads the file, so such a clone attached
    cleanly, merged the owner's allow rules and hook entries, and then made the **withdrawal**
    exit 2 on every run for ever: a repository a clone chose could keep the command that undoes
    an attach from ever completing. Nothing destructive had happened first, because this
    question is asked above every withdrawal -- which is exactly why refusing here is the wrong
    answer. The remedy would be to delete a tracked file out of somebody else's repository, and
    a `detach` that cannot run until you do that is still a `detach` a repository disabled.

    So an unreadable manifest is not a claim of ownership this command will act on, and it is
    not a claim of ownership this command will act *against* either: it leaves the region where
    it is -- the conservative half, since the block may well be the footprint's -- and finishes
    the detach. `Detached.ignore_region_removed` is `False`, which `run_detach` reports, and no
    sentence anywhere says *why* it was left, so nothing here becomes untrue. The remaining
    cost is one block in `.gitignore` that `keelline init` or a hand edit clears, against a
    withdrawal that now always completes.
    """
    try:
        return Manifest.read(root).get("gitignore") is not None
    except Refusal:
        # `Refusal` and not `ManifestError`: a manifest committed as a symlink out of the root is
        # refused by `contained()` as a `PathEscape` before any byte is read, and it blocks the
        # withdrawal exactly as an unparseable one did.
        return True


def _withdraw_ignore_region(root: Path, remaining: str | None) -> bool:
    if remaining is None:
        return False
    # `if remaining` and not `if remaining.strip()`: a `.gitignore` that held only whitespace
    # before the attach is a file the owner had, and the round trip `docs/cli.md` promises is
    # byte-for-byte. Only a file the attach created -- nothing left once its region is gone --
    # is taken away.
    if remaining:
        fsops.write_within(root, GITIGNORE, remaining)
    else:
        fsops.remove_within(root, GITIGNORE)
    return True


def _withdraw_directories(root: Path, recorded: AttachLedger) -> tuple[str, ...]:
    """Remove the directories this repository did not have before the attach, and only those.

    The last step of a detach, after the ledger itself is gone, because `.keelline/local/` holds
    it. `docs/cli.md` promises "an attach and a detach leave the tree byte-for-byte as it was";
    that was false for directories and the test that backed it could not see it, because
    `_snapshot` filters on `is_file()`. Four directories survived every round trip.

    **Three things keep this from deleting somebody's directory.** It walks `CREATED_DIRS`, a
    closed list, and keeps only what the ledger named — so a committed ledger can shorten the
    list, never extend it. The ledger names only what `_absent_directories` found missing before
    the first write, so a directory that was already there is never on it. And the removal is
    `rmdir`: a directory holding anything else at all — the owner's own `.claude/settings.json`,
    a `.codex/rules/` file they wrote by hand, a file some other tool left — survives, and its
    parents then survive with it because they are no longer empty either.

    `ENOTEMPTY` is therefore an ordinary outcome and not a failure, and it is the one this
    `except OSError` is written for: `fsops.rmdir_within` already contains the walk to `root` and
    tolerates an absent target, so what is left is "not empty" and "not permitted", and neither
    is a reason to fail a detach that has already put everything it recorded back.

    Two other things land in the same arm and are meant to. `fsops.UnsafePath` subclasses
    `OSError`, so a component of one of these paths that became a symlink between the check and
    the call is caught here too — the walk refuses it, the directory stays, and the detach
    finishes; that is the same answer "not empty" gets, and the right one for a path this
    function was never going to be able to remove safely. A `PermissionError` is the third, and
    is a fact about the filesystem rather than about the detach.
    """
    removed: list[str] = []
    for name in CREATED_DIRS:
        # `is_dir()` before the call and not only the ledger's say-so: `rmdir_within` tolerates
        # an absent target, so without this a directory the run never created — `.claude/`, when
        # the overlay grants nothing to merge — would be reported as one this detach removed.
        if name not in recorded.directories or not (root / name).is_dir():
            continue
        try:
            fsops.rmdir_within(root, name)
        except OSError:
            continue
        removed.append(name)
    return tuple(removed)


def detach(root: Path, *, machine: Path | None, home: Path | None) -> Detached:
    """Remove exactly what `attach` added, reading the ledger for what that was.

    It does **not** touch `projects/<name>/project.toml`. That record is the owner's consent
    (§6.2), not a piece of local state: deleting it would turn every later re-attach into a
    first attach, and re-ask a question that was already answered.

    `machine` and `home` are keyword-required for the reason every function in this wave takes
    them, and required rather than defaulted for the reason `attach` gives: a resolver without a
    machine file reads the developer's real `~/.config/keelline/`, and the harness link is under
    their real home. A caller that means "the machine owner's own" says `None` out loud.

    **What it may refuse on, and when.** `detach` cannot refuse the way `attach` does once it has
    begun: by the time it reaches the link tree the recorded allow rules, the marked hook entries
    and the `.codex/rules/` copies are already withdrawn, so a refusal there strands a
    half-detached repository. That is why `worktree.detach_main` makes `memory.mode` load-bearing
    through the target it derives rather than refusing on it.

    That is not licence to *discover* a precondition late. Everything structural this function
    can know before its first withdrawal is asked before it: the ledger (which refuses one no
    attach could have written), the configuration (whose loader validates `paths.*`), the
    settings document's own shape through `owned_ids`, whether the footprint owns the ignore
    region, and `_checkouts`, which is the only thing here that needs `git`. What is left after
    the first withdrawal is exactly what cannot precede it — a write that fails, and a component
    of the tree that changed between the check and the removal.

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
    # Asked before the first withdrawal, because it is the one thing here that needs `git` and a
    # `git` that cannot run is knowable at the start. It used to be asked between the settings
    # withdrawal and the link trees, so a machine whose `git` was gone got exit 1 with the
    # settings file and the `.codex/rules/` copies already removed and every link still in place.
    #
    # The anchor for each checkout's harness link is the same shape and is asked in the same
    # breath, with this list as its argument: `detach_main` asks it per checkout from inside the
    # withdrawal, so a home whose `.claude` became a symlink after the attach — a dotfiles
    # manager adopting it is the ordinary way — let a raw `UnsafePath` out of `detach` as
    # `internal error`, with the rule files already deleted and every later run failing at the
    # same line.
    checkouts = _checkouts(root)
    for tree in checkouts:
        harness_anchor(tree, home)
    ignore_remainder = None if _footprint_owns_region(root) else _ignore_region_remainder(root)
    allow_removed = _withdraw_settings(root, recorded)
    rules_removed: list[str] = []
    for rule in recorded.rules:
        if (root / rule).is_file():
            fsops.remove_within(root, rule)
            rules_removed.append(rule)
    # The mirror of `_link_everywhere`, and it had the mirror defect: `detach_main` was applied
    # to `--root` and the loop then skipped the owning checkout unconditionally, so a detach run
    # from a linked worktree withdrew that worktree's tree twice and left the main checkout's
    # link tree — and its harness link — in place. `_checkouts` is the one spelling of "every
    # checkout, owner first, each exactly once" that both halves now read.
    revoked: list[Path] = []
    for tree in checkouts:
        revoked += detach_main(tree, config, machine=machine, home=home).revoked
    region = _withdraw_ignore_region(root, ignore_remainder)
    fsops.remove_within(root, LEDGER)
    # Last, because the ledger lives in one of them.
    directories = _withdraw_directories(root, recorded)
    return Detached(
        allow_removed,
        entries,
        tuple(rules_removed),
        recorded.settings_keys,
        region,
        Links([], revoked),
        directories,
    )
