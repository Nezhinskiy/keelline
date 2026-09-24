"""`keelline upgrade`: the footprint refreshed against the running Keelline.

Every refusal comes before every write.

1. A `keelline.toml` recording a newer Keelline than the one running is refused: moving a project
   backward would repin an older release and put older bytes over newer ones. So is one whose
   version has no leading `X.Y.Z`, whose direction is unknown.
2. `[keelline] version` moves to the running version. Under `[ci] mode = "reusable"` with a
   `[ci] ref` that is a commit, or none yet, the workflow pins Keelline by commit, so `version`,
   `[ci] ref` and the workflow's `uses:` line are one value and move together or not at all.
   When no released commit resolves, or the workflow would not be rewritten to it, neither key
   moves and `held` says why. A `[ci] ref` that is not a commit, such as the documented `v1`
   alias, is the project's own choice to track a moving Keelline: only `version` moves, and
   neither that ref nor the workflow written around it is touched.
3. The footprint pass is re-planned by hash against the manifest; the write-once pass is not.
   An artifact this configuration no longer produces is retired only at a recorded target
   `Prepared.could_write` lists for its id. The workflow is retired only when `[ci] mode` is
   `"none"`: a mode this build merely does not render is not a request to delete the gate. Every
   other record is an orphan, counted and left alone.

Written: the footprint, then `keelline.toml` through `rewrite_owned`, last. An interrupted run
leaves the document naming the old version, and the next run re-plans from there.

What anchors a write, and what does not. Which artifacts exist and which targets each could have
come from this build. The `[paths]` value a target is built from, and the digest a record carries,
come from committed files. For a whole file that means a commit can have this command rewrite it
only while it holds exactly the bytes the same commit records. A managed region is different: it
is inserted into whatever file its `[paths]` key names, recorded or not, so a commit that points
`agents_md` at a tracked file gets the region written into it, and the diff of both shows it.
What no committed value can reach is state git never sees: the loader refuses any `[paths]` value
inside git's control directory or Keelline's own `.keelline/`. That is why `docs/cli.md` says to
run it on a checkout you trust.

What prints is bounded. `Moved.before` is the repository's own value, so a version outside
`X.Y.Z` prints as `(not a version)` and a ref outside `CI_REF` as `(not a commit)`. `Moved.after`
is Keelline's own: the running version, and a sha the release area resolved from the public
repository. `orphans` is a count, because the ids of records this build does not produce are
repository-authored.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import keelline
from keelline.config.loader import loads, read_document
from keelline.config.owned import Value, rewrite
from keelline.config.schema import Config
from keelline.errors import Refusal
from keelline.overlay.api import later
from keelline.project.rewrite import NO_DOCUMENT, rewrite_owned
from keelline.project.templates import (
    CI_REF,
    Prepared,
    project_templates,
    refuse_local_profile,
    refuse_local_root_only,
    retired_templates,
)
from keelline.release.api import Resolution, resolve_pin
from keelline.runner import Runner
from keelline.scaffold import MANIFEST_PATH, Manifest, Plan, Verb, apply, plan

NOT_INITIALISED = (
    f"{MANIFEST_PATH} is not there, so there is no footprint to upgrade; `keelline init` writes one"
)
# Fixed text: the recorded string is repository-authored and is never quoted.
UNREADABLE_VERSION = (
    "keelline.toml's [keelline] version does not begin with a version Keelline can read (X.Y.Z), "
    "so which way upgrade would move it is unknown and nothing was written; set it to the "
    "Keelline release this project was last upgraded with, then run `keelline upgrade` again"
)
NEWER = (
    "keelline.toml records a newer Keelline than the {running} running here, and upgrade never "
    "moves a project backward; update the Keelline plugin, then run `keelline upgrade` with it"
)
_HELD = (
    "[keelline] version and [ci] ref were left as they are: the workflow pins Keelline by "
    "commit, so the two move with it or not at all, and "
)
NO_RELEASE = _HELD + (
    "no released commit of the Keelline running was found; run `keelline upgrade` again once "
    "it is released and the network is reachable"
)
# True in every state that reaches it: the workflow is `skip_modified` at the path the report
# prints (edited by hand, written by somebody else, or kept out of git and not Keelline's bytes),
# and a `--force` naming that path reaches each of those; or the plan refuses it, or the CI line
# says none was rendered, and no flag changes either.
WORKFLOW_HELD = _HELD + (
    "the workflow would not be rewritten to the new pin. When the footprint report lists it "
    "skip_modified, --force with the path printed there moves all three; when the report "
    "refuses it or the CI line says none was rendered, put right what they name, then run "
    "`keelline upgrade` again"
)
_VERSION = re.compile(r"\A[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}\Z")


@dataclass(frozen=True)
class Moved:
    key: str
    before: str
    after: str


@dataclass(frozen=True)
class UpgradeReport:
    footprint: Plan
    moved: tuple[Moved, ...]
    held: str
    resolution: Resolution
    skipped: dict[str, str]
    orphans: int
    dry_run: bool


def _printable(key: str, value: str) -> str:
    if key == "keelline.version":
        return value if _VERSION.match(value) else "(not a version)"
    if not value:
        return "(none)"
    return value if CI_REF.match(value) else "(not a commit)"


def _footprint(
    root: Path,
    config: Config,
    text: str,
    resolution: Resolution,
    force: Sequence[str],
) -> tuple[Prepared, Plan, int]:
    prepared = project_templates(root, config, resolution=resolution, document=text, adopted=False)
    # The placement rule `init` applies, at the second entry point that writes a footprint.
    refuse_local_profile(prepared, config)
    refuse_local_root_only(config)
    produced = {t.id for t in (*prepared.once, *prepared.footprint)}
    retired, orphans = retired_templates(
        prepared.could_write, Manifest.read(root).records, produced
    )
    retired = tuple(t for t in retired if t.id != "ci-workflow" or config.ci.mode == "none")
    # The workflow is planned after everything else, retirements included, so a write that fails
    # part-way leaves its pin agreeing with the `[ci] ref` that `keelline.toml` still holds.
    templates = (*prepared.footprint, *retired)
    ordered = sorted(templates, key=lambda t: t.id == "ci-workflow")
    return prepared, plan(root, config, ordered, force=force), orphans


def _rewrites_the_workflow(footprint: Plan) -> bool:
    return "ci-workflow" in footprint.unchanged or any(
        a.artifact_id == "ci-workflow" and a.verb in (Verb.CREATE, Verb.UPDATE)
        for a in footprint.actions
    )


def upgrade(
    root: Path,
    *,
    machine: Path | None,
    runner: Runner,
    dry_run: bool,
    force: Sequence[str],
) -> UpgradeReport:
    if not (root / MANIFEST_PATH).is_file():
        raise Refusal(NOT_INITIALISED)
    text = read_document(root)
    if text is None:
        raise Refusal(NO_DOCUMENT)
    before = loads(text, root, machine=machine)
    running = keelline.__version__
    # Read by its leading `X.Y.Z`, so `1.0.0-rc1` is newer and not unknown; a value with no
    # leading `X.Y.Z` at all is refused, because moving it could be moving it backward.
    ahead = later(before.keelline.version, running)
    if ahead is None:
        raise Refusal(UNREADABLE_VERSION)
    if ahead:
        raise Refusal(NEWER.format(running=running))
    # A ref that is not a commit (`v1`, the documented opt-in to a moving Keelline) is the
    # project's own and pins nothing this command owns: moving it to a sha, or rendering a
    # workflow over the one written around it, would undo that choice without asking. An empty
    # ref is still pinned: recording one is how a project with no pin yet gets its workflow.
    pinned = before.ci.mode == "reusable" and (
        not before.ci.ref or bool(CI_REF.match(before.ci.ref))
    )
    resolution = resolve_pin(running, runner, cwd=root) if pinned else Resolution(None, True)
    changes: dict[tuple[str, str], Value] = {("keelline", "version"): running}
    held = ""
    # The pure editor, to learn what the document would become before anything is written; the
    # one write of `keelline.toml` below still goes through `rewrite_owned`, which re-stamps the
    # `config` record with it.
    if pinned and resolution.pin is not None:
        changes[("ci", "ref")] = resolution.pin.sha
    elif pinned and rewrite(text, changes) != text:
        changes, held = {}, NO_RELEASE
    document = rewrite(text, changes)
    config = loads(document, root, machine=machine)
    prepared, footprint, orphans = _footprint(root, config, text, resolution, force)
    if pinned and document != text and not _rewrites_the_workflow(footprint):
        changes, held, config = {}, WORKFLOW_HELD, before
        prepared, footprint, orphans = _footprint(root, config, text, resolution, force)
    moved = tuple(
        Moved(key, _printable(key, old), new)
        for key, old, new in (
            ("keelline.version", before.keelline.version, config.keelline.version),
            ("ci.ref", before.ci.ref, config.ci.ref),
        )
        if old != new
    )
    report = UpgradeReport(footprint, moved, held, resolution, prepared.skipped, orphans, dry_run)
    if dry_run or footprint.refusals:
        return report
    apply(root, footprint)
    rewrite_owned(root, changes)
    return report
