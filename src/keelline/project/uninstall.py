"""`keelline uninstall`: `upgrade`'s rule run backwards.

Every artifact the manifest records is retired: one this build still produces with its own
template, one it no longer produces at a recorded target `Prepared.could_write` lists for its id,
whatever `[ci] mode` says now. `[artifacts] local` artifacts are never recorded and are retired by
id. The engine then removes a whole file while its bytes are Keelline's, takes a region out of a
file (and the file, if nothing else was in it), and leaves anything else in place and listed.
`--force PATH` takes a listed file anyway. Records naming an id this build does not produce, or a
target it could not have written, are counted and never touched.

**A region leaves as a region.** A record this build no longer produces is judged against a
whole-file stub, which names no region, so `retired_templates` never retires a record whose kind
says it lived inside a host file: it is counted as an orphan, by the one rule `upgrade` applies
too. A region comes out only through the template this build produces for it.

**What anchors a removal, and what a commit can move.** Which artifact ids exist, which targets
each could have, and every region's name are this build's: constants in the installed package
that no repository can extend. The `[paths]` value a target is built from, and the digest a record
carries, come from committed files. So a commit can have this command remove only a whole file
whose exact bytes the same commit records, or the region a template of this build names, and its
diff shows the `[paths]` edit and the record. The kind a record carries is committed too, and all
it can do here is turn a removal into an orphan. Nothing committed reaches `.git/` or
`.keelline/`: the loader refuses a `[paths]` value inside either, and the manifest is read through
`contained()`, so a symlinked `.keelline/` is a refusal. That is the whole boundary, and why
`docs/cli.md` says to run it on a checkout you trust.

**Two passes, footprint first.** `AGENTS.md` holds the write-once skeleton and the footprint's
`harness` region. Once the region is out, an untouched skeleton is byte-identical to the one
recorded, and the write-once pass removes it. The dry run judges the skeleton with its region still
in, and `ORDER_NOTE` says so. `--force` never reaches the write-once pass at a path the footprint
pass also targets: forcing `AGENTS.md` forces Keelline's region out of it, and the skeleton, with
whatever a person wrote into it, is then judged on its own bytes.

**The ignore region last, and only over nothing.** The footprint's `.gitignore` region is the
only thing keeping `.keelline/local/` out of git, so it is taken out in a third pass, after the
disk shows nothing left under `.keelline/local/`. If something is left, the run stops before that
pass, with the region and the manifest in place, so git still ignores the files, and once they
are moved out the next run can finish (`KEPT_AFTER`).

**Directories as each pass goes, then `keelline.toml`, then the ledger.** Every directory above
a file a pass removed goes once it is empty, when the pass ends or stops (`_apply`), and no other:
a `[paths]` value is committed, so a directory it merely names may be a person's. Then
`keelline.toml`, whose removal the write-once pass holds back for this point, then
`.keelline/assessment.json`, the manifest, and `.keelline/` once it is empty. So a run stopped at
any earlier point leaves the configuration and the manifest the next run needs to finish it. A
process killed mid-pass can leave an empty directory behind, which no later run removes.

**Two refusals come before any write**: while the repository is attached, and while
`.keelline/local/` holds a file this run would not remove, the local-only memory notes above all.
That count is a prediction from the plans: a file goes only when an action unlinks it, or when
a region's removal leaves exactly what the write-once pass then removes, which the engine's own
rule for a file kept out of git (`matches_render`) answers before anything is written. An edited
region, or a skeleton a person wrote into that shares the region's file, keeps the file, so the
run refuses before it writes rather than part-way. The check above stays as the fact behind the
prediction. It counts and never names a path, and a dry run reports it instead of refusing, even
when a plan refuses, so the report that lists an edited local artifact is still printed.

**A refusal while writing is not a refusal before it.** The engine keeps what it applied, and
records it, when a later write or removal fails; so does this command across its passes. Exit 2
then means "stopped part-way": what was done is on disk and in the manifest, `keelline.toml` is
still there, and running the command again re-plans from there to the end.

**Without `keelline.toml`, nothing can be judged.** While the manifest still records the file
(`CONFIG_RECORD`), something other than this command took it, a person deleting it above all:
this command's own removal goes through `apply`, which drops the record with the file. Going on
would drop the manifest and leave every recorded file untracked for good, so the run refuses
before any write and says to restore the file (`DELETED_CONFIG`). With no such record, either a
run stopped after removing it and before the manifest, or the file was the project's own and
never recorded; then the ledger goes, every recorded file stays, and the note gives their
count, so the next run converges instead of refusing for ever. No directory is pruned on that
path: nothing says where this configuration put its artifacts, and a target the manifest
records is a committed string.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from keelline.attach.api import LEDGER
from keelline.config.loader import loads, read_document
from keelline.config.paths import KEELLINE_DIRECTORY, contained
from keelline.errors import Refusal
from keelline.fsops import remove_within, rmdir_within
from keelline.project.rewrite import CONFIG_RECORD
from keelline.project.templates import (
    project_templates,
    refuse_local_root_only,
    retired_templates,
)
from keelline.release.api import Resolution
from keelline.scaffold import (
    LOCAL_ROOT,
    MANIFEST_PATH,
    Action,
    Location,
    Manifest,
    Plan,
    Template,
    Verb,
    apply,
    effective_target,
    matches_render,
    plan,
    unlinks,
)

NOTHING = (
    f"{MANIFEST_PATH} is not there; nothing records what Keelline wrote here, so there is "
    "nothing to uninstall"
)
ATTACHED = (
    "this repository is attached to an overlay; run `keelline detach` first — uninstall takes "
    "out the ignore block that keeps what attach wrote out of git"
)
KEPT_LOCALLY = (
    f"{LOCAL_ROOT}/ holds {{count}} file(s) uninstall would not remove, and the ignore block it "
    "takes out is what keeps them out of git: local-only memory notes, or an artifact kept out "
    "of git that was edited. uninstall refuses until they are moved out of it; an edited "
    "artifact in a file of its own there can instead be named with --force"
)
KEPT_AFTER = (
    f"{LOCAL_ROOT}/ still holds {{count}} file(s) after the other removals, so the ignore block "
    "that keeps them out of git and the manifest were left in place; move them out, then run "
    "uninstall again"
)
ORDER_NOTE = (
    "AGENTS.md is judged twice: the dry run sees the skeleton with Keelline's region still in "
    "it and calls it edited, and the real run takes the region out first and judges what is left"
)
# The footprint's ignore region: what keeps `.keelline/local/` out of git, so it goes last.
IGNORE = "gitignore"
NO_CONFIG = (
    "keelline.toml is not there, so nothing the manifest records can be judged: those {count} "
    "file(s) stay where they are, and only the ledger goes"
)
# Fixed text. The manifest still records `keelline.toml`, so something other than this command's
# own removal took it (`apply` drops the record with the file), and git can usually give it back.
DELETED_CONFIG = (
    "keelline.toml is not there while .keelline/manifest.json still records it; without it "
    "nothing the manifest records can be judged, and going on would leave those files untracked "
    "for good, so nothing was removed. Restore keelline.toml (from git, for instance), then run "
    "uninstall again"
)
ASSESSMENT = f"{KEELLINE_DIRECTORY}/assessment.json"
LEDGER_DIRS = (LOCAL_ROOT, KEELLINE_DIRECTORY)


@dataclass(frozen=True)
class UninstallReport:
    footprint: Plan
    once: Plan
    orphans: int
    dry_run: bool
    note: str
    kept_locally: int


def _retire(templates: Sequence[Template], ids: Set[str]) -> tuple[Template, ...]:
    return tuple(replace(t, retired=True) for t in templates if t.id in ids)


def _kept_locally(root: Path, removing: Set[str]) -> int:
    """How many files under `LOCAL_ROOT` this run leaves behind: counted, never named."""
    base = contained(root, LOCAL_ROOT)
    kept = (p for p in base.rglob("*") if p.is_symlink() or not p.is_dir())
    return sum(1 for p in kept if f"{LOCAL_ROOT}/{p.relative_to(base).as_posix()}" not in removing)


def _rmdirs(root: Path, directories: Set[str]) -> None:
    """Remove each directory that is empty, deepest first; leave every other one.

    Each is asked only whether it is empty: `rmdir` refuses a directory with anything in it,
    which is the whole safety of the walk, and a refusal of any kind (`UnsafePath` is an
    `OSError`) leaves the directory where it is. A harness's own directory is never asked
    (`Harness.marker_dir`). It is the harness's before it is Keelline's, and detection reads its
    presence, so an empty one stays whoever made it: nothing records whether a person or `init`
    did, and `docs/cli.md` says a later `init` detects the harness until it is removed.
    """
    from keelline.harnesses import HARNESSES

    marker_dirs = {harness.marker_dir for harness in HARNESSES}
    for directory in sorted(directories, key=lambda d: d.count("/"), reverse=True):
        if directory in marker_dirs:
            continue
        with contextlib.suppress(OSError):
            rmdir_within(root, directory)


def _prune(root: Path, removed: Sequence[str]) -> None:
    """Every directory above a file this run removed, once it is empty.

    Only those. It used to be every directory above every place this configuration puts an
    artifact, and a place is a committed `[paths]` value: `roadmap = "some/dir/x.md"` had the
    run remove an empty `some/dir/` a person made, a git-ignored placeholder included, though
    nothing of Keelline's was ever in it. A directory above a file this run took held that file
    when the run began, so emptying it is this run's doing.
    """
    _rmdirs(
        root,
        {
            parent.as_posix()
            for target in removed
            for parent in PurePosixPath(target).parents
            if parent.as_posix() != "."
        },
    )


def _apply(root: Path, planned: Plan) -> None:
    """`apply`, then `_prune` over what it removed, whether or not it finished.

    In a `finally`, so a pass that stops part-way still empties the directories of the files it
    took: the run that finishes it cannot tell a directory an earlier run emptied from one a
    person left empty, so it would never prune one. What counts as removed is a file an action
    of this plan unlinks that is no longer there; `plan` never unlinks a file it did not read.
    """
    try:
        apply(root, planned)
    finally:
        removed = [a.target for a in planned.actions if unlinks(a)]
        _prune(root, [target for target in removed if not os.path.lexists(root / target)])


def _remove_ledger(root: Path) -> None:
    """`.keelline/assessment.json`, the manifest last, then `.keelline/` once it is empty.

    A directory where a ledger file belongs is not a file Keelline wrote; it is left where it is,
    and so is `.keelline/` around it, rather than refusing every later run before the manifest
    goes.
    """
    for target in (ASSESSMENT, MANIFEST_PATH.as_posix()):
        path = root / target
        if path.is_dir() and not path.is_symlink():
            continue
        try:
            remove_within(root, target)
        except OSError as exc:
            raise Refusal(f"{target} cannot be removed: {exc}") from exc
    _rmdirs(root, set(LEDGER_DIRS))


def uninstall(
    root: Path, *, machine: Path | None, dry_run: bool, force: Sequence[str]
) -> UninstallReport:
    if not (root / MANIFEST_PATH).is_file():
        raise Refusal(NOTHING)
    if (root / LEDGER).is_file():
        raise Refusal(ATTACHED)
    manifest = Manifest.read(root)
    document = read_document(root)
    if document is None:
        if CONFIG_RECORD in manifest.records:
            raise Refusal(DELETED_CONFIG)
        # Only the ledger: without the configuration nothing says where its artifacts were, and a
        # target the manifest records is a committed string. No run of this command reaches here
        # with directories it emptied, because `keelline.toml` goes after they are pruned.
        if not dry_run:
            _remove_ledger(root)
        note = NO_CONFIG.format(count=len(manifest.records))
        return UninstallReport(Plan(), Plan(), 0, dry_run, note, 0)
    config = loads(document, root, machine=machine)
    refuse_local_root_only(config)
    prepared = project_templates(
        root, config, resolution=Resolution(None, True), document=document, adopted=True
    )
    produced = {t.id for t in (*prepared.once, *prepared.footprint)}
    retired, orphans = retired_templates(prepared.could_write, manifest.records, produced)
    wanted = set(manifest.records) | set(config.artifacts.local)
    footprint_retired = (*_retire(prepared.footprint, wanted), *retired)
    once_retired = _retire(prepared.once, wanted)
    # `keelline.toml` goes last of all, after the ignore pass and the directories: while it and
    # the manifest are there, a run stopped at any earlier point is finished by the next one.
    once_body = [t for t in once_retired if t.id != CONFIG_RECORD]
    config_retired = [t for t in once_retired if t.id == CONFIG_RECORD]
    # Paths as the engine resolves them: an `[artifacts] local` target lives under
    # `.keelline/local/artifacts/`, which `Template.target` does not say.
    footprint_targets = {effective_target(t, config)[0] for t in footprint_retired}
    once_force = tuple(path for path in force if path not in footprint_targets)
    footprint = plan(root, config, footprint_retired, force=force)
    once = plan(root, config, once_retired, force=once_force)
    note = ORDER_NOTE if dry_run else ""
    # Before any write, how many files under `.keelline/local/` the run would leave. A file goes
    # only when an action unlinks it, or when a region's removal leaves the bytes the write-once
    # pass will then remove: the engine's own verdict for a file kept out of git, asked of those
    # bytes now. Only such a file matters here, since no `[paths]` value reaches `.keelline/`.
    local_once = {
        target: template
        for template in once_body
        for target, location in [effective_target(template, config)]
        if location is Location.LOCAL
    }
    unlinked = {a.target for a in footprint.actions if _goes(a, local_once)}
    unlinked |= {a.target for a in once.actions if unlinks(a)}
    kept = _kept_locally(root, unlinked)
    if dry_run or footprint.refusals or once.refusals:
        return UninstallReport(footprint, once, orphans, dry_run, note, kept)
    if kept:
        raise Refusal(KEPT_LOCALLY.format(count=kept))
    body = plan(root, config, [t for t in footprint_retired if t.id != IGNORE], force=force)
    _apply(root, body)
    # Re-planned once the region is out of `AGENTS.md`, so an untouched skeleton is judged on the
    # bytes `init` recorded. The report carries the plans that ran, not the prediction above.
    judged = plan(root, config, once_body, force=once_force)
    _apply(root, judged)
    # What is on disk now decides, not the prediction: while anything is left under
    # `.keelline/local/`, the ignore region stays, and so does the manifest that records it.
    left = _kept_locally(root, frozenset())
    if left:
        raise Refusal(KEPT_AFTER.format(count=left))
    ignore = plan(root, config, [t for t in footprint_retired if t.id == IGNORE], force=force)
    _apply(root, ignore)
    last = plan(root, config, config_retired, force=once_force)
    _apply(root, last)
    _remove_ledger(root)
    return UninstallReport(_joined(body, ignore), _joined(judged, last), orphans, dry_run, note, 0)


def _goes(action: Action, local_once: Mapping[str, Template]) -> bool:
    """Whether the file `action` targets is gone once both passes ran: it unlinks it, or it takes
    a region out of a file kept out of git and leaves exactly what the write-once pass removes.
    A `REMOVE` with a payload keeps the file for the footprint pass, and a `SKIP_MODIFIED` keeps
    it for good. A forced path never reaches the write-once pass at such a target, so this is
    the whole of what that pass will do there."""
    if unlinks(action):
        return True
    template = local_once.get(action.target)
    return (
        action.verb is Verb.REMOVE
        and action.payload is not None
        and template is not None
        and matches_render(template, action.payload)
    )


def _joined(first: Plan, second: Plan) -> Plan:
    return Plan(
        actions=(*first.actions, *second.actions),
        refusals=(*first.refusals, *second.refusals),
        unchanged=(*first.unchanged, *second.unchanged),
    )
