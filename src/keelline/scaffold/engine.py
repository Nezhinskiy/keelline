"""Decide, then write: the scaffold engine's contract.

`plan` reads and decides; `apply` writes. The split is what makes `--dry-run` honest — the
report a user approves is produced by the same code path that then runs — and it is what makes
the containment rule testable without a filesystem full of traps.

Two rules are easy to state and easy to get backwards, so they are stated here once.

*An absent record does not mean "hands off" for every kind.* For a whole file it does: a file
Keelline never wrote is somebody's. For a managed region and for keyed entries the file
belongs to somebody by definition, and an absent record is the ordinary first install — the
rules for regions and for keyed entries exist for exactly that case. The hand-edit oracle for
those two kinds is the region body and the marked entries, never the file around them.

*A refusal is an artifact's, not the plan's.* A file that cannot be read, a region whose markers
no longer say where it ends, a settings document that is not JSON: each is recorded in
`Plan.refusals` and the remaining templates are still decided. `plan` raises only for input no
per-artifact report could rescue — the configured profile, the manifest itself, and a malformed
`Template`, which is a bug in the lane that built it rather than a file a user can put right.
Both shapes of malformed `Template` raise, symmetrically: a managed region that names no
region, and keyed entries that name no entries. The second did not, and `entries or {}` turned
it into a silent uninstall of whatever the user had wired up.

*Containment is not a string check.* `contained()` decides whether a path may be written;
`fsops.open_within` decides what is actually written to, by walking the path with `O_NOFOLLOW`
and handing back a descriptor. A component can still become a symlink after `contained()` has
passed — that is the race this layer exists to survive — but it cannot redirect the write: the
walk fails the open rather than following the link, and the string is never resolved a second
time, not for the write and not for the parent directories, which `fsops.mkdirs_within`
creates one component at a time through the same walk rather than with `Path.mkdir`.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from keelline.config.paths import PathEscape, contained
from keelline.config.schema import PROJECT_NAME, Config
from keelline.errors import Refusal
from keelline.fsops import UnsafePath, remove_within, write_within
from keelline.scaffold.entries import ENTRY_MARKER, EntriesError, apply_entries, owned, unmarked
from keelline.scaffold.manifest import Kind, Location, Manifest, Record, digest
from keelline.scaffold.model import WRITING, Action, Applied, Plan, Refused, Template, Verb
from keelline.scaffold.regions import RegionError, drop, extract, upsert

LOCAL_ROOT = ".keelline/local"
# `[artifacts] local` artifacts live one directory further down, so no `[artifacts] local` entry
# can land one on a file another lane keeps under `LOCAL_ROOT`: attach's ledger, the local-only
# note store. `PATH_VALUE` refuses a `..` segment, so for that setting the prefix is a boundary
# and not a convention; the anchor is this constant in the installed package. A `[paths]` value
# never reaches `.keelline/` at all: `config.paths.validate_paths` refuses one that names it.
LOCAL_ARTIFACTS = f"{LOCAL_ROOT}/artifacts"
# The reason a local artifact is left alone. It is never recorded, so the one oracle for
# "Keelline's bytes" is what this build renders, and anything else may be an edit in a directory
# git will not give back.
NOT_OURS_LOCALLY = "kept out of git, and not the bytes this Keelline writes"
SOURCE_NAME = PROJECT_NAME  # the one name grammar, `config.schema.PROJECT_NAME`
SOURCE_RULE = "lowercase letters, digits, `.`, `_` and `-`, starting with a letter or digit"
_IN_FILE = (Kind.MANAGED_REGION, Kind.KEYED_ENTRIES)
# The two refusals that belong to one artifact's own file: a region whose markers no longer say
# where it ends, and a settings document that cannot be parsed. Both are ordinary user state — a
# bad merge, a half-typed edit — and both are answered per artifact. `Refusal` itself is
# deliberately not caught: `_payload_and_stamp` raises it for a `MANAGED_REGION` template
# carrying no region name and for a `KEYED_ENTRIES` template carrying no entries, each a
# malformed `Template` and so a bug in the lane that built it, not something a user can put
# right by editing a file.
_OWN_FILE_REFUSALS = (RegionError, EntriesError)
_VERB_FOR = {Kind.MANAGED_REGION: Verb.REGION_UPDATE, Kind.KEYED_ENTRIES: Verb.ENTRIES_UPDATE}


def shipped_profiles() -> tuple[str, ...]:
    """The profile names this build carries, from the package itself.

    `keelline.profiles.shipped()` lists a directory under the package only when it holds a
    `profile.toml`, and the package is the one listing: it answers for an installed wheel and a
    `src/` checkout alike.
    """
    from keelline.profiles import shipped

    return shipped()


def validate_sources(config: Config) -> None:
    """Path containment's second rule: the two values that name a file inside the *plugin* root.

    "Inside the project root" cannot bound them by construction, so each is validated as one
    path segment and looked up against the listing. The preset half is already enforced by the
    configuration loader through `presets.load_preset`; the profile half is enforced here,
    because the loader stores `profile` as a bare string and widening `Config` would change a
    frozen contract.
    """
    profile = config.keelline.profile
    if not profile:
        return
    # Named and never quoted, in both refusals: `profile` is repository-authored, and the first
    # runs exactly for a value outside `SOURCE_NAME`, which can hold ESC and line breaks. The
    # rule is stated in words and the listing is Keelline's own, so nothing here is the clone's.
    if not SOURCE_NAME.match(profile):
        raise PathEscape(f"[keelline] profile is not one path segment ({SOURCE_RULE})")
    shipped = shipped_profiles()
    if profile not in shipped:
        known = ", ".join(shipped) or "none"
        raise PathEscape(
            "[keelline] profile names a profile this version of Keelline does not ship "
            f"(available: {known})"
        )


def effective_target(template: Template, config: Config) -> tuple[str, Location]:
    """Where `plan` puts `template` under `config`, and whether that place is kept out of git.

    An `[artifacts] local` artifact lives under `LOCAL_ARTIFACTS`, which `Template.target` does
    not say, so a caller comparing paths the way the engine does asks this rather than
    re-deriving it.
    """
    if template.id in config.artifacts.local:
        return f"{LOCAL_ARTIFACTS}/{template.target}", Location.LOCAL
    return template.target, Location.REPO


def unlinks(action: Action) -> bool:
    """Whether applying `action` deletes its file. A `REMOVE` with a payload rewrites the file
    with what is left once Keelline's part is out, so the file stays."""
    return action.verb is Verb.REMOVE and action.payload is None


def matches_render(template: Template, current: str) -> bool:
    """Whether `current` holds exactly the bytes this build renders for `template`'s part of it.

    The one oracle for an `[artifacts] local` artifact, which is never recorded: `plan` removes a
    retired one only while this answers yes, unless its path is forced. Public so a caller that
    must predict that verdict for text not yet on disk asks the engine rather than re-deriving it.
    """
    _, stamp = _payload_and_stamp(template, current)
    present = _present_stamp(template, current)
    return present is not None and digest(present) == digest(stamp)


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
        if template.entries is None:
            # `{}` means "remove every Keelline entry", and `Template.entries` defaults to
            # `None` — so `template.entries or {}` read a lane that forgot one keyword argument
            # as a lane asking to uninstall the user's hook wiring, reported the result as
            # `entries_update` / "refreshed", and rewrote the manifest as though it were an
            # ordinary upgrade. The malformed-`Template` rule five lines above is the same
            # rule: a bug in the lane that built it, raised rather than acted on. `{}` is left
            # to mean removal, for the caller that genuinely wants it.
            raise Refusal(f"{template.id}: a keyed-entries template names no entries")
        if missing := unmarked(template.entries):
            # The same defect class as the branch above, in the other direction, and it landed
            # the other way round: `entries=None` silently *uninstalled* the user's wiring,
            # while entries carrying no `# keelline:<id>` marker silently fail to install it.
            # `owned()` renders the marked entries alone, so with none marked it answers `{}`
            # for both the payload and what is already on disk, the digests match, and the
            # artifact is reported `unchanged` — the report says "up to date" about a file
            # nothing wrote. A lane that did not call `entries.mark` is a bug in that lane,
            # raised rather than acted on, exactly like a malformed `Template` above.
            raise Refusal(
                f"{template.id}: a keyed-entries template carries {len(missing)} entry/entries "
                f"with no `{ENTRY_MARKER}<id>` marker, so nothing could ever recognise them as "
                f"Keelline's own: {', '.join(repr(command) for command in missing)}"
            )
        document = apply_entries(current or "", template.entries)
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
    """What `remove` leaves behind.

    Nothing for a whole file. For the two kinds that live inside somebody else's file, the file
    minus Keelline's part, and nothing either when Keelline's part was all the file held, which
    is what `detach` already does with the `.gitignore` it emptied. Emptiness is exact: a
    remainder of whitespace is somebody's and stays. A host file that already existed and was
    empty before the region went in is removed with the region, as `detach` removes it.
    """
    if template.kind is Kind.MANAGED_REGION and template.region is not None:
        remainder = drop(current, template.region, template.style)
        return remainder if remainder else None
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
        target, location = effective_target(template, config)
        try:
            path = contained(root, target, resolved_root=resolved_root)
        except PathEscape as exc:
            refusals.append(Refused(template.id, target, str(exc)))
            continue

        record = manifest.get(template.id)
        if record is not None and record.target != target:
            # The relocation reads and rewrites the artifact's own old file, so a refusal from
            # it is this artifact's refusal — the same rule the block below runs under.
            try:
                moved = _relocation(root, resolved_root, template, record)
            except _OWN_FILE_REFUSALS as exc:
                refusals.append(Refused(template.id, record.target, str(exc)))
                continue
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
                _plan_retired(
                    template, record, current, target, location, forced, actions, unchanged
                )
                continue
            if template.kind is Kind.ONCE and current is not None:
                # `skip_modified`, which is the plan's decision table (row: "no record, file
                # present, kind is `template` or `once`"), and not `unchanged`, which is what
                # this said. The plan contradicts itself between that row and its prose, so the
                # choice is recorded here: `unchanged` renders as "up to date", and Keelline has
                # no idea whether this file is up to date — a create-once artifact is one it
                # deliberately never looks inside again. "Left alone because it is yours" is the
                # true statement, and it is the one the user can act on.
                actions.append(
                    Action(
                        Verb.SKIP_MODIFIED,
                        template.id,
                        target,
                        None,
                        "create-once, and the file is already there",
                        None,
                    )
                )
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
            if (
                record is None
                and location is Location.REPO
                and template.kind not in _IN_FILE
                and target not in forced
            ):
                # A whole file Keelline never wrote is somebody's; a region or a hook entry
                # inside a file Keelline never wrote is the ordinary first install. A local
                # artifact is answered by the next branch instead: it is never recorded, so
                # `record is None` there says nothing about who wrote the file.
                #
                # `--force PATH` reaches this file too, which is the whole-file rule: differs,
                # so skip it and name it, and `--force <path>` overwrites it. `forced` is the
                # caller's argv and `target` the path `plan` derived and contained above, so no
                # committed file can force anything; without it a caller workflow a person wrote
                # held `upgrade`'s version and pin back for ever, with no flag that moved them.
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
            if (
                record is None
                and location is Location.LOCAL
                and present is not None
                and target not in forced
            ):
                actions.append(
                    Action(Verb.SKIP_MODIFIED, template.id, target, None, NOT_OURS_LOCALLY, None)
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

    # The conversion to tuples happens here, at the boundary, so the object a user approves
    # through `render_report` is the object `apply` consumes. See `Plan`.
    return Plan(actions=tuple(actions), refusals=tuple(refusals), unchanged=tuple(unchanged))


def _relocation(root: Path, resolved_root: Path, template: Template, record: Record) -> Action:
    """A recorded artifact whose effective target moved — `[artifacts] local` gained or lost its id.

    The recorded target is repository-controlled through the committed manifest, so "does this
    record describe the file I am about to delete" cannot rest on the record alone: a committed
    manifest naming any in-root file, stamped with the bytes that file is committed with, would
    otherwise make `plan` emit a `REMOVE` for it. So the recorded target must be one of the two
    paths this template can produce — its configured target, or that target under
    `LOCAL_ARTIFACTS` — before anything else is asked. It is then contained before it is read,
    exactly like a configured one.

    **Always an `Action`, never `None`.** Every branch that declines to remove the old file used
    to answer `None`, and `plan` read that as "nothing to do here" and carried on creating the
    file at the new target — so a relocated artifact whose old file a user had hand-edited was
    left on disk holding that edit, the manifest ended empty, and the report said "0 skipped,
    0 refused". `apply`'s own comment calls that state a defect: "a file Keelline wrote carrying
    no record, which every later run reads as somebody else's … invisible to `uninstall`". The
    symmetric `_plan_retired` path has always emitted `skip_modified` for it.

    So the three ways the old file is not Keelline's to remove — a recorded target this template
    could not have produced, one that no longer contains, and one whose bytes are not the ones
    recorded — each become a `skip_modified` naming the old path and saying which it was.
    """
    if record.target not in (template.target, f"{LOCAL_ARTIFACTS}/{template.target}"):
        return _left_behind(
            template,
            record,
            "the manifest records a target this artifact cannot produce, so the file at it "
            "is not Keelline's to remove",
        )
    try:
        old_path = contained(root, record.target, resolved_root=resolved_root)
    except PathEscape as exc:
        return _left_behind(template, record, str(exc))
    old, reason = _read(old_path)
    if reason is not None:
        return _left_behind(template, record, reason)
    if old is None:
        # Nothing at the old path: the move has effectively already happened, and there is no
        # file to leave behind. A `skip_modified` here would report a file that is not there.
        return Action(Verb.REMOVE, template.id, record.target, None, "relocated", record)
    # What the record stamps is what `_payload_and_stamp` stamped: the whole file for a whole
    # file, and Keelline's own part of it for a region or a set of keyed entries. Comparing the
    # whole old file with a region's stamp read every real relocation of a region as a hand edit.
    present = _present_stamp(template, old)
    if present is None or digest(present) != record.sha256:
        return _left_behind(template, record, "relocated and hand-edited")
    # The same payload `_plan_retired` computes, and for the same reason: for a managed region
    # or a set of keyed entries the file at the old path belongs to somebody else, so what
    # leaves is Keelline's own part of it and not the file.
    payload = _removal_payload(template, old)
    return Action(Verb.REMOVE, template.id, record.target, payload, "relocated", record)


def _left_behind(template: Template, record: Record, reason: str) -> Action:
    return Action(Verb.SKIP_MODIFIED, template.id, record.target, None, reason, None)


def _plan_retired(
    template: Template,
    record: Record | None,
    current: str | None,
    target: str,
    location: Location,
    forced: set[str],
    actions: list[Action],
    unchanged: list[str],
) -> None:
    if current is None:
        unchanged.append(template.id)
        return
    if location is Location.LOCAL:
        # No record exists for a local artifact, so it is judged against this build's own
        # render, the one oracle it has. The directory is git-ignored: an edit removed here is
        # one git cannot give back, so a file that is not exactly Keelline's goes only when forced.
        ours = matches_render(template, current)
        if ours or target in forced:
            payload = _removal_payload(template, current)
            reason = "retired" if ours else "retired, forced"
            actions.append(Action(Verb.REMOVE, template.id, target, payload, reason, None))
        else:
            reason = f"retired, {NOT_OURS_LOCALLY}"
            actions.append(Action(Verb.SKIP_MODIFIED, template.id, target, None, reason, None))
        return
    if record is None:
        unchanged.append(template.id)
        return
    present = _present_stamp(template, current)
    matches = present is not None and digest(present) == record.sha256
    # `force` reaches a retired artifact the user edited and has decided to remove anyway: the
    # one file a removal's `--force PATH` names. For a region what goes is still the region and
    # never the file around it: forcing overrides the hand-edit verdict, not the payload.
    #
    # The path compared is `target`, the effective target `plan` derived from this template and
    # `[artifacts] local` and then contained, exactly as the live-template check in `plan` does;
    # never `record.target`, which the committed manifest supplies. The two are equal here only
    # because `plan` drops a record whose target differs, so comparing the effective one means
    # no manifest a clone commits can decide which file a `--force PATH` reaches.
    if matches or target in forced:
        actions.append(
            Action(
                Verb.REMOVE,
                template.id,
                record.target,
                _removal_payload(template, current),
                "retired" if matches else "retired, forced",
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

    # The ledger records what is on disk, so it is persisted for the actions that ran even when
    # a later one refuses. Discarding it would leave a file Keelline wrote carrying no record,
    # which every later run reads as somebody else's: `skip_modified` under a false reason,
    # moved only by a `--force` that names it, and invisible to `uninstall`. The refusal still
    # propagates; only the loop is wrapped, because the refusal above it has written nothing to
    # record.
    try:
        for action in planned.actions:
            if action.verb is Verb.SKIP_MODIFIED:
                skipped.append(action.target)
                continue
            # Re-validate the string against the live tree, then stop using the string: the
            # write happens through a descriptor `open_within` walked with O_NOFOLLOW.
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
    finally:
        manifest.write(root)

    return Applied(written=tuple(written), removed=tuple(removed), skipped=tuple(skipped))


def _write(root: Path, target: str, payload: str) -> None:
    """Create the parents and replace the file, or refuse — never raise a bare `OSError`.

    The walk, the parent creation and the atomic replacement are `fsops.write_within`; what is
    this area's is the translation below. That split is deliberate: `attach`, `setup`,
    `overlay` and `hooks-core` all write files that are not `Template`s, and the half they need
    is the walk, not this area's verdict vocabulary.

    The second clause is what keeps the refusal exit code, 2, reachable. A user who saves a file
    where a directory component belongs while reading the dry-run report, then confirms, would
    otherwise get a traceback instead of a refusal, and no race is needed for that.
    """
    try:
        write_within(root, target, payload)
    except UnsafePath as exc:
        raise Refusal(str(exc)) from exc
    except OSError as exc:
        raise Refusal(f"{target} cannot be written: {exc}") from exc


def _remove(root: Path, target: str, payload: str | None) -> None:
    """Unlink the file, or rewrite it without Keelline's part — never raise a bare `OSError`.

    The same second clause `_write` carries, for the same reason: a directory Keelline may read
    but not write to arrives here as EACCES from `os.unlink` rather than as an `UnsafePath`, and
    only a refusal keeps the refusal exit code, 2, reachable.
    """
    if payload is not None:
        _write(root, target, payload)
        return
    try:
        remove_within(root, target)
    except UnsafePath as exc:
        raise Refusal(str(exc)) from exc
    except OSError as exc:
        raise Refusal(f"{target} cannot be removed: {exc}") from exc
