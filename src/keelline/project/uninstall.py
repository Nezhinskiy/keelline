"""`keelline uninstall`: `upgrade`'s rule run backwards.

Every artifact the manifest records is retired: one this build still produces with its own
template, one it no longer produces at a recorded target `Prepared.could_write` lists for its id,
whatever `[ci] mode` says now. `[artifacts] local` artifacts are never recorded and are retired by
id. The engine then removes a whole file while its bytes are Keelline's, takes a region out of a
file (and the file, if nothing else was in it), and leaves anything else in place and listed.
`--force PATH` takes a listed file anyway. Records naming an id this build does not produce, or a
target it could not have written, are counted and never touched.

**A region leaves as a region.** A record this build no longer produces is judged against a
whole-file stub, which names no region, so a record whose kind says it lived inside a host file
is never retired that way: forced, the stub would delete the host file and everything a person
wrote in it. It is counted as an orphan instead. A region comes out only through the template
this build produces for it, which carries the region's name and comment style.

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
pass, with the region and the manifest in place, so git still ignores the files and the next run
can finish (`KEPT_AFTER`).

**Then the ledger:** `.keelline/assessment.json`, the manifest, and `.keelline/` once it is empty.

**Two refusals come before any write**: while the repository is attached, and while
`.keelline/local/` holds a file this run would not remove, the local-only memory notes above all.
That count is a prediction from the plans: a file goes only when an action unlinks it, and a
remainder the write-once pass will judge after the first pass ran is left to that pass and to the
check above. It counts and never names a path, and a dry run reports it instead of refusing, so
the report that lists an edited local artifact is still printed.

**A refusal while writing is not a refusal before it.** The engine keeps what it applied, and
records it, when a later write or removal fails; so does this command across its passes. Exit 2
then means "stopped part-way": what was done is on disk and in the manifest, and running the
command again re-plans from there.

**Without `keelline.toml`, nothing can be judged.** A run that died after its write-once pass, or
a person who deleted the file, leaves a manifest and no configuration. The ledger goes, every
recorded file stays, and the note gives their count, so the next run converges instead of
refusing for ever.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence, Set
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from keelline.attach.api import LEDGER
from keelline.config.loader import loads, read_document
from keelline.config.paths import contained
from keelline.errors import Refusal
from keelline.fsops import UnsafePath, remove_within, rmdir_within
from keelline.project.templates import project_templates, retired_templates
from keelline.release.api import Resolution
from keelline.scaffold import (
    LOCAL_ROOT,
    MANIFEST_PATH,
    Kind,
    Manifest,
    Plan,
    Template,
    apply,
    effective_target,
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
    "of git that was edited. uninstall refuses until they are moved out of it, or an edited "
    "artifact is named with --force"
)
KEPT_AFTER = (
    f"{LOCAL_ROOT}/ still holds {{count}} file(s) after the other removals, so the ignore block "
    "that keeps them out of git and the manifest were left in place; move them out or name them "
    "with --force, then run uninstall again"
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
ASSESSMENT = ".keelline/assessment.json"
LEDGER_DIRS = (LOCAL_ROOT, ".keelline")
# The kinds that live inside a file somebody else owns.
IN_FILE = frozenset({Kind.MANAGED_REGION, Kind.KEYED_ENTRIES})


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


def _prune(root: Path, removed: Sequence[str]) -> None:
    """The ledger, then every directory a removed file leaves empty, deepest first.

    Only the parents of the places this configuration puts an artifact are asked, whichever run
    removed the file: a run stopped part-way removed some of them and their records, and the run
    that finishes must still empty their directories. Each is asked only whether it is empty:
    `rmdir` refuses a directory with anything in it, which is the whole safety of the walk.
    A harness's own directory is never asked (`Harness.marker_dir`). It is the harness's before it
    is Keelline's, and detection reads its presence, so an empty harness directory a person made
    stays.
    """
    from keelline.harnesses import HARNESSES

    marker_dirs = {harness.marker_dir for harness in HARNESSES}
    # The manifest last: while it is there, the next run can still finish this one.
    for target in (ASSESSMENT, MANIFEST_PATH.as_posix()):
        try:
            remove_within(root, target)
        except OSError as exc:
            raise Refusal(f"{target} cannot be removed: {exc}") from exc
    parents = {
        parent.as_posix()
        for target in (*removed, MANIFEST_PATH.as_posix())
        for parent in PurePosixPath(target).parents
        if parent.as_posix() != "."
    }
    for directory in sorted(parents | set(LEDGER_DIRS), key=lambda d: d.count("/"), reverse=True):
        if directory in marker_dirs:
            continue
        with contextlib.suppress(OSError, UnsafePath):
            rmdir_within(root, directory)


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
        if not dry_run:
            _prune(root, ())
        note = NO_CONFIG.format(count=len(manifest.records))
        return UninstallReport(Plan(), Plan(), 0, dry_run, note, 0)
    config = loads(document, root, machine=machine)
    prepared = project_templates(
        root, config, resolution=Resolution(None, True), document=document, adopted=True
    )
    recorded = {artifact_id: r.target for artifact_id, r in manifest.records.items()}
    produced = {t.id for t in (*prepared.once, *prepared.footprint)}
    # A record kept inside a host file that this build does not produce is an orphan: see the
    # module docstring's "A region leaves as a region".
    in_file = {i for i, r in manifest.records.items() if r.kind in IN_FILE and i not in produced}
    whole = {i: target for i, target in recorded.items() if i not in in_file}
    retired, orphans = retired_templates(prepared.could_write, whole, produced)
    orphans += len(in_file)
    wanted = set(recorded) | set(config.artifacts.local)
    footprint_retired = (*_retire(prepared.footprint, wanted), *retired)
    once_retired = _retire(prepared.once, wanted)
    # Paths as the engine resolves them: an `[artifacts] local` target lives under
    # `.keelline/local/artifacts/`, which `Template.target` does not say.
    footprint_targets = {effective_target(t, config)[0] for t in footprint_retired}
    once_targets = {effective_target(t, config)[0] for t in once_retired}
    once_force = tuple(path for path in force if path not in footprint_targets)
    # Every place this configuration puts an artifact, recorded or not: a run stopped part-way
    # already removed some files and their records, and their directories are still this run's.
    places = {effective_target(t, config)[0] for t in (*prepared.once, *prepared.footprint)}
    footprint = plan(root, config, footprint_retired, force=force)
    once = plan(root, config, once_retired, force=once_force)
    note = ORDER_NOTE if dry_run else ""
    if footprint.refusals or once.refusals:
        return UninstallReport(footprint, once, orphans, dry_run, note, 0)
    # A file goes only when an action unlinks it. A remainder at a write-once target is judged by
    # that pass after the first one ran, so it is left to that pass and to the check after it.
    unlinked = {a.target for a in footprint.actions if unlinks(a) or a.target in once_targets}
    unlinked |= {a.target for a in once.actions if unlinks(a)}
    kept = _kept_locally(root, unlinked)
    if dry_run:
        return UninstallReport(footprint, once, orphans, dry_run, note, kept)
    if kept:
        raise Refusal(KEPT_LOCALLY.format(count=kept))
    body = plan(root, config, [t for t in footprint_retired if t.id != IGNORE], force=force)
    apply(root, body)
    # Re-planned once the region is out of `AGENTS.md`, so an untouched skeleton is judged on the
    # bytes `init` recorded. The report carries the plans that ran, not the prediction above.
    judged = plan(root, config, once_retired, force=once_force)
    apply(root, judged)
    # What is on disk now decides, not the prediction: while anything is left under
    # `.keelline/local/`, the ignore region stays, and so does the manifest that records it.
    left = _kept_locally(root, frozenset())
    if left:
        raise Refusal(KEPT_AFTER.format(count=left))
    ignore = plan(root, config, [t for t in footprint_retired if t.id == IGNORE], force=force)
    apply(root, ignore)
    _prune(root, sorted(places | footprint_targets | once_targets))
    ran = Plan(
        actions=(*body.actions, *ignore.actions),
        refusals=(*body.refusals, *ignore.refusals),
        unchanged=(*body.unchanged, *ignore.unchanged),
    )
    return UninstallReport(ran, judged, orphans, dry_run, note, 0)
