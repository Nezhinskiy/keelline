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
    PROJECT_CODEX,
    PermissionDiff,
    diff_permissions,
    local_document,
    overlay_entries,
    settings_document,
)
from keelline.errors import Failure, Refusal
from keelline.memory.api import PROJECT_RECORD, PROJECTS
from keelline.overlay.api import COMMON_CODEX, Runner
from keelline.scaffold import EntriesError, Style, apply_entries, marker_id, upsert

LEDGER = ".keelline/local/attach.json"
LEDGER_FORMAT = 1
GITIGNORE = ".gitignore"
IGNORE_REGION = "ignore"
# §7.1 lists both: the ledger's directory, and the assessment file `assess` will write.
IGNORED = (".keelline/local/", ".keelline/assessment.json")
IGNORE_NOTE = "# Keelline's local state: yours, never a collaborator's."
CODEX_RULES = ".codex/rules"
PRE_COMMIT_CONFIG = ".pre-commit-config.yaml"
PRE_COMMIT_HOOK = Path(".git") / "hooks" / "pre-commit"


@dataclass(frozen=True)
class Attached:
    """What one `attach` changed. Nothing here is repository-authored, so all of it may print."""

    settings_written: bool
    rules_written: tuple[str, ...]
    binding_recorded: bool
    ignored: bool
    notes: tuple[str, ...]


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
    if not diff.added_allow and not wanted:
        # Nothing to add, so nothing is touched. A rewrite here would reformat a file the owner
        # owns, on a run that changed nothing, and report itself as a write.
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
    shared path would hide which. This project's own directory is read second, so a file it
    shares a name with in `common/` is the one that lands.
    """
    written: dict[str, None] = {}
    sources = (
        binding.overlay / COMMON_CODEX,
        binding.overlay / PROJECTS / binding.project / PROJECT_CODEX,
    )
    for source in sources:
        if not source.is_dir():
            continue
        for rule in sorted(source.iterdir()):
            if not rule.is_file() or rule.name.startswith("."):
                continue
            target = f"{CODEX_RULES}/{rule.name}"
            fsops.write_within(root, target, rule.read_text(encoding="utf-8"))
            written[target] = None
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
    if (binding.overlay / PRE_COMMIT_HOOK).exists():
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
    root: Path, binding: Binding, diff: PermissionDiff, rules: tuple[str, ...]
) -> None:
    """Record what this attach may remove again — the union with what an earlier one claimed.

    The union is not a nicety. A second attach against an unchanged overlay has an *empty*
    diff, because every rule is already present, so a ledger written from the diff alone would
    forget what the first one added and leave `detach` nothing to remove.
    """
    previous = _existing_ledger(root)
    allow = list(previous.allow) if previous is not None else []
    allow += [rule for rule in diff.added_allow if rule not in allow]
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
        "rules": list(rules),
    }
    fsops.write_within(root, LEDGER, json.dumps(document, indent=2, sort_keys=True) + "\n")


def attach(
    root: Path,
    *,
    store: Path,
    machine: Path | None,
    confirmed: bool,
    trust_remote: bool,
    runner: Runner,
) -> Attached:
    """Bind this repository to the overlay and merge what the overlay grants.

    The order is the order the refusals have to happen in: read the binding, which already
    refuses a store outside the machine-recorded overlay; compute the diff; refuse a widening
    without `confirmed`; refuse a mismatch without `trust_remote`; then write, `.gitignore`
    first.

    `runner` is the seam the `overlay` lane introduced, and it is a parameter rather than a
    default so that no test can reach a real `pre-commit`.
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
            f"the overlay records a different remote for project {binding.project!r}, so this "
            f"is not the repository it was bound to; pass --trust-remote only if it should be"
        )
    _write_ignore_region(root)
    rules = _codex_rules(root, binding)
    document = local_document(root)
    merged = _merged_settings(document, diff, binding)
    written = merged != document
    if written:
        fsops.write_within(root, LOCAL_SETTINGS, merged)
    _write_ledger(root, binding, diff, rules)
    recorded = _record_binding(binding)
    note = _secret_scan(binding, runner)
    return Attached(written, rules, recorded, True, () if note is None else (note,))
