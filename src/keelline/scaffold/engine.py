"""Decide, then write (contract C2).

`plan` reads and decides; `apply` writes. The split is what makes `--dry-run` honest — the
report a user approves is produced by the same code path that then runs — and it is what makes
the containment rule testable without a filesystem full of traps.

Two rules are easy to state and easy to get backwards, so they are stated here once.

*An absent record does not mean "hands off" for every kind.* For a whole file it does: a file
Keelline never wrote is somebody's. For a managed region and for keyed entries the file
belongs to somebody by definition, and an absent record is the ordinary first install — §7.2's
second and third rows exist for exactly that case. The hand-edit oracle for those two kinds is
the region body and the marked entries, never the file around them.

*A refusal is an artifact's, not the plan's.* A file that cannot be read, a region whose markers
no longer say where it ends, a settings document that is not JSON: each is recorded in
`Plan.refusals` and the remaining templates are still decided. `plan` raises only for input the
whole plan rests on — the configured profile, and the manifest itself.

*Containment is not a string check.* `contained()` decides whether a path may be written;
`fsops.open_within` decides what is actually written to, by walking the path with `O_NOFOLLOW`
and handing back a descriptor. Between the two there is no window in which a component can
become a symlink, because the string is never resolved a second time — not for the write, and
not for the parent directories, which `_mkdirs_within` creates one component at a time through
the same walk rather than with `Path.mkdir`.
"""

from __future__ import annotations

import contextlib
import os
import re
from collections.abc import Sequence
from importlib import resources
from pathlib import Path, PurePosixPath

from keelline.config.paths import PathEscape, contained
from keelline.config.schema import Config
from keelline.errors import Refusal
from keelline.fsops import UnsafePath, open_within, write_atomically_at
from keelline.scaffold.entries import EntriesError, apply_entries, owned
from keelline.scaffold.manifest import Kind, Location, Manifest, Record, digest
from keelline.scaffold.model import WRITING, Action, Applied, Plan, Refused, Template, Verb
from keelline.scaffold.regions import RegionError, drop, extract, upsert

LOCAL_ROOT = ".keelline/local"
SOURCE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_IN_FILE = (Kind.MANAGED_REGION, Kind.KEYED_ENTRIES)
# The two refusals that belong to one artifact's own file: a region whose markers no longer say
# where it ends, and a settings document that cannot be parsed. Both are ordinary user state — a
# bad merge, a half-typed edit — and both are answered per artifact. `Refusal` itself is
# deliberately not caught: `_payload_and_stamp` raises it for a `MANAGED_REGION` template
# carrying no region name, which is a malformed `Template` and so a bug in the lane that built
# it, not something a user can put right by editing a file.
_OWN_FILE_REFUSALS = (RegionError, EntriesError)
_VERB_FOR = {Kind.MANAGED_REGION: Verb.REGION_UPDATE, Kind.KEYED_ENTRIES: Verb.ENTRIES_UPDATE}


def shipped_profiles() -> list[str] | None:
    """The profile names this build carries, or `None` while no `profiles/` exists anywhere.

    `None` is not an empty list, and the difference is the whole point: §5.1 draws `profiles/`
    at the repository root while the package reads its own data from inside the wheel, and the
    lane that creates either runs in wave 5. Until then there is no listing to check against,
    and refusing every non-empty name would make `init --yes` on a Python repository produce a
    configuration that `plan()` rejects outright.
    """
    package = resources.files("keelline").joinpath("profiles")
    if package.is_dir():
        return sorted(entry.name for entry in package.iterdir())
    root = Path(__file__).resolve().parents[3] / "profiles"
    if root.is_dir():
        return sorted(entry.name for entry in root.iterdir())
    return None


def validate_sources(config: Config) -> None:
    """§7.4's second rule: the two values that name a file inside the *plugin* root.

    "Inside the project root" cannot bound them by construction, so each is validated as one
    path segment and, when a listing exists, looked up against it. The preset half is already
    enforced by C1's loader through `presets.load_preset`; the profile half is enforced here,
    because C1 stores `profile` as a bare string and widening `Config` would change a frozen
    contract.
    """
    profile = config.keelline.profile
    if not profile:
        return
    if not SOURCE_NAME.match(profile):
        raise PathEscape(
            f"[keelline] profile {profile!r} is not one path segment matching {SOURCE_NAME.pattern}"
        )
    shipped = shipped_profiles()
    if shipped is not None and profile not in shipped:
        known = ", ".join(shipped) or "none"
        raise PathEscape(
            f"[keelline] profile {profile!r} is not shipped with this version of Keelline "
            f"(available: {known})"
        )


def _effective_target(template: Template, config: Config) -> tuple[str, Location]:
    if template.id in config.artifacts.local:
        return f"{LOCAL_ROOT}/{template.target}", Location.LOCAL
    return template.target, Location.REPO


def _read(path: Path) -> tuple[str | None, str | None]:
    """`(content, reason)`: a reason is a refusal for this one artifact, never for the plan.

    `newline=""` and not `read_text`: universal-newline translation turns every `\\r\\n` and
    every lone `\\r` into `\\n` before `regions.py` is reached, and `regions.py` is the module
    promising to return every byte outside its own markers unchanged. Translating on the way in
    makes that promise false for a CRLF file no matter how carefully the rewrite is done.
    """
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            return stream.read(), None
    except FileNotFoundError:
        return None, None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{path} cannot be read: {exc}"


def _payload_and_stamp(template: Template, current: str | None) -> tuple[str, str]:
    """The text `apply` writes, and the text whose digest the manifest records.

    They differ for the two kinds that live inside a file somebody else owns: what is written
    is the whole file, what is recorded is only Keelline's own part of it.
    """
    if template.kind is Kind.MANAGED_REGION:
        if template.region is None:
            raise Refusal(f"{template.id}: a managed-region template names no region")
        body = template.render()
        return upsert(current or "", template.region, body, template.style), body.rstrip("\r\n")
    if template.kind is Kind.KEYED_ENTRIES:
        document = apply_entries(current or "", template.entries or {})
        return document, owned(document)
    body = template.render()
    return body, body


def _present_stamp(template: Template, current: str) -> str | None:
    if template.kind is Kind.MANAGED_REGION:
        if template.region is None:
            return None
        return extract(current, template.region, template.style)
    if template.kind is Kind.KEYED_ENTRIES:
        return owned(current)
    return current


def _removal_payload(template: Template, current: str) -> str | None:
    """What `remove` leaves behind: nothing for a whole file, the file minus Keelline's part
    for the two kinds that live inside somebody else's (§7.3)."""
    if template.kind is Kind.MANAGED_REGION and template.region is not None:
        return drop(current, template.region, template.style)
    if template.kind is Kind.KEYED_ENTRIES:
        return apply_entries(current, {})
    return None


def plan(
    root: Path,
    config: Config,
    templates: Sequence[Template],
    *,
    force: Sequence[str] = (),
) -> Plan:
    validate_sources(config)
    manifest = Manifest.read(root)
    resolved_root = root.resolve()
    forced = set(force)
    actions: list[Action] = []
    refusals: list[Refused] = []
    unchanged: list[str] = []

    for template in templates:
        target, location = _effective_target(template, config)
        try:
            path = contained(root, target, resolved_root=resolved_root)
        except PathEscape as exc:
            refusals.append(Refused(template.id, target, str(exc)))
            continue

        record = manifest.get(template.id)
        if record is not None and record.target != target:
            moved = _relocation(root, resolved_root, template, record)
            if moved is not None:
                actions.append(moved)
            record = None

        current, reason = _read(path)
        if reason is not None:
            refusals.append(Refused(template.id, target, reason))
            continue

        # Everything below reads or rewrites this one artifact's own file, so a refusal from it
        # is this artifact's refusal. Letting one escape would hide every other template and
        # leave `upgrade` with no report at all — including the REFUSED section that exists to
        # name exactly these.
        try:
            if template.retired:
                _plan_retired(template, record, current, actions, unchanged)
                continue
            if template.kind is Kind.ONCE and current is not None:
                unchanged.append(template.id)
                continue

            payload, stamp = _payload_and_stamp(template, current)
            new_record = Record(
                id=template.id,
                kind=template.kind,
                location=location,
                target=target,
                template=template.source,
                version=config.keelline.version,
                sha256=digest(stamp),
            )
            if current is None:
                actions.append(Action(Verb.CREATE, template.id, target, payload, "new", new_record))
                continue

            present = _present_stamp(template, current)
            if present is not None and digest(present) == digest(stamp):
                unchanged.append(template.id)
                continue
            if record is None and template.kind not in _IN_FILE:
                # A whole file Keelline never wrote is somebody's; a region or a hook entry
                # inside a file Keelline never wrote is the ordinary first install (§7.2, rows
                # 2 and 3).
                actions.append(
                    Action(
                        Verb.SKIP_MODIFIED,
                        template.id,
                        target,
                        None,
                        "exists and Keelline did not write it",
                        None,
                    )
                )
                continue
            hand_edited = (
                record is not None and present is not None and digest(present) != record.sha256
            )
            if hand_edited and target not in forced:
                actions.append(
                    Action(Verb.SKIP_MODIFIED, template.id, target, None, "hand-edited", None)
                )
                continue
            verb = _VERB_FOR.get(template.kind, Verb.UPDATE)
            actions.append(Action(verb, template.id, target, payload, "refreshed", new_record))
        except _OWN_FILE_REFUSALS as exc:
            refusals.append(Refused(template.id, target, str(exc)))

    return Plan(actions=actions, refusals=refusals, unchanged=unchanged)


def _relocation(
    root: Path, resolved_root: Path, template: Template, record: Record
) -> Action | None:
    """A recorded artifact whose effective target moved — `[artifacts] local` gained its id.

    The recorded target is repository-controlled through the committed manifest, so it is
    contained before it is read, exactly like a configured one.
    """
    try:
        old_path = contained(root, record.target, resolved_root=resolved_root)
    except PathEscape:
        return None
    old, reason = _read(old_path)
    if reason is not None or old is None or digest(old) != record.sha256:
        return None
    return Action(Verb.REMOVE, template.id, record.target, None, "relocated", record)


def _plan_retired(
    template: Template,
    record: Record | None,
    current: str | None,
    actions: list[Action],
    unchanged: list[str],
) -> None:
    if record is None or current is None:
        unchanged.append(template.id)
        return
    present = _present_stamp(template, current)
    if present is not None and digest(present) == record.sha256:
        actions.append(
            Action(
                Verb.REMOVE,
                template.id,
                record.target,
                _removal_payload(template, current),
                "retired",
                record,
            )
        )
        return
    actions.append(
        Action(
            Verb.SKIP_MODIFIED, template.id, record.target, None, "retired and hand-edited", None
        )
    )


def apply(root: Path, planned: Plan) -> Applied:
    """Write what `plan` decided, or refuse the whole plan.

    `apply` takes the `Plan` rather than a bare action list, and no `force`: a refusal is a
    property of the plan, and forcing is a decision `plan` already made. A caller that wants
    the good half of a refused plan re-plans without the offending templates.
    """
    if planned.refusals:
        detail = "; ".join(f"{r.artifact_id}: {r.reason}" for r in planned.refusals)
        raise Refusal(f"{len(planned.refusals)} path(s) refused: {detail}")

    manifest = Manifest.read(root)
    resolved_root = root.resolve()
    written: list[str] = []
    removed: list[str] = []
    skipped: list[str] = []

    for action in planned.actions:
        if action.verb is Verb.SKIP_MODIFIED:
            skipped.append(action.target)
            continue
        # Re-validate the string against the live tree, then stop using the string: the write
        # happens through a descriptor `open_within` walked with O_NOFOLLOW.
        contained(root, action.target, resolved_root=resolved_root)
        if action.verb is Verb.REMOVE:
            _remove(root, action.target, action.payload)
            removed.append(action.target)
            manifest = manifest.without(frozenset({action.artifact_id}))
            continue
        if action.verb in WRITING:
            if action.payload is None:
                raise Refusal(f"{action.artifact_id}: {action.verb} with no payload")
            _write(root, action.target, action.payload)
            written.append(action.target)
            if action.record is not None and action.record.location is Location.REPO:
                manifest = manifest.with_record(action.record)
            else:
                manifest = manifest.without(frozenset({action.artifact_id}))

    manifest.write(root)
    return Applied(written=written, removed=removed, skipped=skipped)


def _mkdirs_within(root: Path, target: str) -> None:
    """Create `target`'s parent directories without ever leaving the root.

    `Path.mkdir(parents=True)` cannot do this job: it takes a string and it follows symlinks,
    so a component that became a link after `contained()` passed makes it create directories
    outside the root — and it creates them before the `O_NOFOLLOW` walk gets a chance to
    refuse. Each component here is created relative to a descriptor the walk just opened, so a
    symlink anywhere along the path refuses with nothing created.
    """
    parts = PurePosixPath(target).parts[:-1]
    for depth in range(len(parts)):
        branch = "/".join(parts[: depth + 1])
        with open_within(root, branch) as (dir_fd, name), contextlib.suppress(FileExistsError):
            os.mkdir(name, dir_fd=dir_fd)


def _write(root: Path, target: str, payload: str) -> None:
    """Create the parents and replace the file, or refuse — never raise a bare `OSError`.

    The second clause is what keeps C5's exit 2 reachable. A user who saves a file where a
    directory component belongs while reading the dry-run report, then confirms, would
    otherwise get a traceback instead of a refusal, and no race is needed for that.
    """
    try:
        _mkdirs_within(root, target)
        with open_within(root, target) as (dir_fd, name):
            write_atomically_at(dir_fd, name, payload)
    except UnsafePath as exc:
        raise Refusal(str(exc)) from exc
    except OSError as exc:
        raise Refusal(f"{target} cannot be written: {exc}") from exc


def _remove(root: Path, target: str, payload: str | None) -> None:
    if payload is not None:
        _write(root, target, payload)
        return
    try:
        with open_within(root, target) as (dir_fd, name), contextlib.suppress(FileNotFoundError):
            os.unlink(name, dir_fd=dir_fd)
    except UnsafePath as exc:
        raise Refusal(str(exc)) from exc
