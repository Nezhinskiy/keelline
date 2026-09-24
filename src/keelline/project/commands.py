"""The project area's commands: `init` writes a repository's Keelline footprint once, `upgrade`
refreshes it, and `uninstall` takes it back.

**The summary is both rendered reports, the way `overlay upgrade`'s is.** It was four lines of
counts, with every artifact's verb and the whole REFUSED section reachable only under `--json`
— so the skill that tells a relayer to pass on "both reports" and "every refused line" was
describing output the command did not print, and the exit-1 path is the one a person meets
without a flag. `scaffold.render_report` is the renderer, and the same text goes into `--json`
under `once` and `footprint`, so the two cannot disagree.

That is safe on the repository-bytes rule because `render_report` bounds every target it
prints: one outside `PATH_VALUE`, such as a target a committed manifest recorded, prints as its
artifact id. The reason beside it is the engine's own fixed vocabulary. The CI line is one of
this area's fixed sentences, or a tag and a commit the *release* area resolved from the public
repository's own tags. The project's name and its `[ci]` values reach none of them.

**The workflow is claimed only when nothing skipped it, and the ref it names is the one on
disk.** `_ci` reaches its `GATE_BRANCH` check *after* the pin has resolved, so a repository with
a resolved tag and a `gate_branch` outside the grammar has a pin and no workflow; keying the CI
line on the pin told that repository `CI: <tag>@<sha>` while `skipped["ci-workflow"]` said the
opposite in `--json`. The key in `skipped` is the authority — `_ci` returns a template or a
reason and never both — and `report.ref` is the second half: on the adoption path the workflow
pins the ref `keelline.toml` already carried rather than one this run resolved, so the line says
that instead of naming a release the file does not record.

**Exit 1 on a refusal, not 2.** A refused artifact is a finding the report names, and `apply`
was never reached: nothing was written, there is no manifest, and re-running after the fix is
the whole remedy. That is `overlay upgrade`'s rule, and this command follows it so a caller
scripting over both reads one number. Exit 2 stays what it is everywhere — a refusal raised
above the plans, such as a missing `--yes` or a repository that is already initialised.
"""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath

from keelline.areas import SubParsers
from keelline.command import DRY_RUN_HELP, common_flags
from keelline.errors import Refusal
from keelline.result import Result
from keelline.scaffold import Plan, Verb, printable, render_report

# What the flag does and what it does not: it sets `[ci] mode` in the document this run builds,
# and on the adoption path that document is a `Kind.ONCE` artifact already on disk — reported
# `skip_modified`, never rewritten — so the file goes on saying `reusable` and the flag is spent
# on this run alone. Saying "sets [ci] mode" flat sent an operator looking for a key nothing wrote.
NO_CI_HELP = (
    'write no CI workflow and ask no remote for a pin; sets [ci] mode = "none" in the document '
    "this run builds, which on a repository that already has a keelline.toml is this run only"
)
# `(refused, dry_run)` -> the opening line. Three states and not two: a refused run wrote
# nothing, and it used to open `initialised:` above a REFUSED section saying the opposite. That
# was invisible while the summary was four count lines; printing the report is what made the
# header a claim a reader checks. A dry run that also refuses is reported as the refusal,
# because that is the finding the operator has to act on before either sentence is true.
HEADINGS = {
    (True, True): "refused, and nothing would be written:",
    (True, False): "refused, and nothing was written:",
    (False, True): "would initialise:",
    (False, False): "initialised:",
}
# A count and fixed text: `[keelline] agents` is repository-authored, so its names never print.
UNKNOWN_HARNESSES = (
    "note: {count} name(s) in [keelline] agents name no harness this Keelline serves; those "
    "harnesses were given the AGENTS.md region only"
)
YES_HELP = (
    "accept the detected defaults and write the footprint; without it nothing is written and "
    "the command refuses, naming the lane that ships the questions"
)


def run_init(args: argparse.Namespace) -> Result:
    from keelline.project.init import init
    from keelline.runner import subprocess_runner

    root = Path(args.root).resolve()
    machine = Path(args.machine) if args.machine else None
    report = init(
        root,
        machine=machine,
        runner=subprocess_runner(),
        yes=args.yes,
        dry_run=args.dry_run,
        ci=args.ci,
    )
    once, footprint = render_report(report.once), render_report(report.footprint)
    pin = report.resolution.pin
    skipped = report.skipped.get("ci-workflow")
    # `skipped is not None` is the whole condition, and the `or not report.ref` that stood
    # beside it and the `or 'no workflow was planned'` under it were both unreachable.
    # `templates._ci` returns a rendered workflow only for a non-empty `[ci] ref` that matches
    # `CI_REF`, and returns a non-empty reason in every other arm; `init` then derives
    # `report.ref` as `"" if "ci-workflow" in prepared.skipped else config.ci.ref`. So a run
    # with no skip has a ref, the fallback string could never be formatted, and the disjunct
    # could never be the reason this branch was taken. `init`'s own comment calls the two "one
    # value by construction" and `doctor`'s `ci-ref` row enforces it; an unreachable arm that
    # would print a sentence nobody can provoke is the same species as a vacuous assertion,
    # and this repository deletes those.
    if skipped is not None:
        ci_line = f"CI: skipped — {skipped}"
    elif pin is not None and pin.sha == report.ref:
        ci_line = f"CI: {pin.tag}@{pin.sha}"
    else:
        ci_line = "CI: the workflow pins the [ci] ref this repository already recorded"
    refused = bool(report.once.refusals or report.footprint.refusals)
    lines = [
        HEADINGS[(refused, report.dry_run)],
        "",
        "write-once:",
        once,
        "",
        "footprint:",
        footprint,
        "",
        ci_line,
    ]
    if report.note:
        lines.append(f"note: {report.note}")
    if report.unknown_harnesses:
        lines.append(UNKNOWN_HARNESSES.format(count=report.unknown_harnesses))
    data = {
        "dry_run": report.dry_run,
        "adopted": report.adopted,
        "once": once,
        "footprint": footprint,
        "writes": [*report.once.writes, *report.footprint.writes],
        "skipped": dict(report.skipped),
        "pin": None if pin is None else {"tag": pin.tag, "sha": pin.sha},
        "asked": report.resolution.asked,
        "note": report.note,
        "ref": report.ref,
        "unknown_harnesses": report.unknown_harnesses,
    }
    return Result("\n".join(lines), data, exit_code=1 if refused else 0)


# The refused lines are `init`'s, word for word: a refused plan wrote nothing, whichever command
# planned it.
UPGRADE_HEADINGS = {**HEADINGS, (False, True): "would upgrade:", (False, False): "upgraded:"}
FORCE_HELP = (
    "overwrite or remove this hand-edited file anyway, as a path relative to --root; repeat for "
    "each file, and never for one you did not mean"
)
# Fixed text: the value is what the operator typed, and the rule is what they can act on.
FORCE_OUTSIDE = "--force takes a path relative to --root, with no '..' component"
FORCE_UNMATCHED = (
    "note: {count} --force path(s) named no file this run had to judge, so they forced nothing; "
    "a path is compared exactly, relative to --root"
)
# The `upgrade` CI line when a workflow was rendered. Keyed on what the plan does with it, not on
# the absence of a skip reason: a workflow the report lists `skip_modified` (edited by hand, or
# never Keelline's) or refuses is left as it is, and may pin anything at all.
CI_PINNED = "CI: the workflow pins [ci] ref"
CI_LEFT = (
    "CI: the workflow was left as it is, so what it pins is not this run's to say; the "
    "footprint report names it and why"
)
# A count: the ids of records this build does not produce are repository-authored.
ORPHANS = (
    "note: {count} record(s) in .keelline/manifest.json name artifacts this Keelline does not "
    "produce; they were left where they are"
)


def _force_paths(raw: list[str]) -> tuple[str, ...]:
    """Each `--force` value as the engine compares it: root-relative, with a leading `./` gone.

    An absolute path or one with a `..` component is refused naming the rule, never the value.
    """
    paths: list[str] = []
    for value in raw:
        path = PurePosixPath(value.removeprefix("./"))
        if path.is_absolute() or ".." in path.parts:
            raise Refusal(FORCE_OUTSIDE)
        paths.append(path.as_posix())
    return tuple(paths)


def _unmatched(force: tuple[str, ...], *plans: Plan) -> int:
    """How many forced paths no planned action names: a typo, or a file with nothing to force."""
    targets = {action.target for planned in plans for action in planned.actions}
    return sum(1 for path in force if path not in targets)


def run_upgrade(args: argparse.Namespace) -> Result:
    from keelline.project.upgrade import upgrade
    from keelline.runner import subprocess_runner

    force = _force_paths(args.force)
    report = upgrade(
        Path(args.root).resolve(),
        machine=Path(args.machine) if args.machine else None,
        runner=subprocess_runner(),
        dry_run=args.dry_run,
        force=force,
    )
    refused = bool(report.footprint.refusals)
    moved = "; ".join(
        f"[{m.key.split('.')[0]}] {m.key.split('.')[1]} {m.before} -> {m.after}"
        for m in report.moved
    )
    shown = render_report(report.footprint)
    lines = [
        UPGRADE_HEADINGS[(refused, report.dry_run)],
        f"keelline.toml: {moved or 'nothing to move'}",
        "footprint:",
        shown,
    ]
    skipped = report.skipped.get("ci-workflow")
    if skipped:
        lines.append(f"CI: skipped — {skipped}")
    else:
        lines.append(CI_PINNED if report.workflow_current else CI_LEFT)
    if report.held:
        lines.append(f"note: {report.held}")
    if report.orphans:
        lines.append(ORPHANS.format(count=report.orphans))
    if unmatched := _unmatched(force, report.footprint):
        lines.append(FORCE_UNMATCHED.format(count=unmatched))
    pin = report.resolution.pin
    data = {
        "dry_run": report.dry_run,
        "moved": [{"key": m.key, "before": m.before, "after": m.after} for m in report.moved],
        "held": report.held,
        "footprint": shown,
        "writes": report.footprint.writes,
        "skipped": dict(report.skipped),
        "orphans": report.orphans,
        "pin": {"tag": pin.tag, "sha": pin.sha} if pin else None,
        "asked": report.resolution.asked,
    }
    return Result("\n".join(lines), data, exit_code=1 if refused else 0)


# The refused lines are `init`'s in substance, with the verb this command performs.
UNINSTALL_HEADINGS = {
    (True, True): "refused, and nothing would be removed:",
    (True, False): "refused, and nothing was removed:",
    (False, True): "would uninstall:",
    (False, False): "uninstalled:",
}


def run_uninstall(args: argparse.Namespace) -> Result:
    from keelline.project.uninstall import KEPT_LOCALLY, uninstall

    force = _force_paths(args.force)
    report = uninstall(
        Path(args.root).resolve(),
        machine=Path(args.machine) if args.machine else None,
        dry_run=args.dry_run,
        force=force,
    )
    refused = bool(report.footprint.refusals or report.once.refusals)
    # Through `printable`, the bound the reports use, so a forged target is `<id>` in both.
    left = sorted(
        printable(a)
        for a in (*report.footprint.actions, *report.once.actions)
        if a.verb is Verb.SKIP_MODIFIED
    )
    footprint, once = render_report(report.footprint), render_report(report.once)
    lines = [
        UNINSTALL_HEADINGS[(refused, report.dry_run)],
        "footprint:",
        footprint,
        "write-once:",
        once,
    ]
    if left:
        lines.append(f"left in place, yours now: {len(left)} file(s), each named above")
    if report.orphans:
        lines.append(ORPHANS.format(count=report.orphans))
    if report.note:
        lines.append(f"note: {report.note}")
    if report.kept_locally:
        lines.append(f"note: {KEPT_LOCALLY.format(count=report.kept_locally)}")
    if unmatched := _unmatched(force, report.footprint, report.once):
        lines.append(FORCE_UNMATCHED.format(count=unmatched))
    data = {
        "dry_run": report.dry_run,
        "footprint": footprint,
        "once": once,
        "left": left,
        "orphans": report.orphans,
        "note": report.note,
        "kept_locally": report.kept_locally,
    }
    return Result("\n".join(lines), data, exit_code=1 if refused else 0)


def register(groups: SubParsers) -> None:
    # `parser` and not `init`: the name `init` in this module is the command, and the function
    # `run_init` imports from `keelline.project.init`.
    parser = common_flags(groups.add_parser("init", help="write this repository's footprint"))
    parser.add_argument("--yes", action="store_true", help=YES_HELP)
    parser.add_argument("--dry-run", action="store_true", help=DRY_RUN_HELP)
    parser.add_argument("--no-ci", dest="ci", action="store_false", help=NO_CI_HELP)
    parser.set_defaults(func=run_init, ci=True)
    upgrade = common_flags(groups.add_parser("upgrade", help="refresh this repository's footprint"))
    upgrade.add_argument("--dry-run", action="store_true", help=DRY_RUN_HELP)
    upgrade.add_argument("--force", action="append", default=[], metavar="PATH", help=FORCE_HELP)
    upgrade.set_defaults(func=run_upgrade)
    uninstall = common_flags(
        groups.add_parser(
            "uninstall", help="remove this repository's footprint; leave what you edited"
        )
    )
    uninstall.add_argument("--dry-run", action="store_true", help=DRY_RUN_HELP)
    uninstall.add_argument("--force", action="append", default=[], metavar="PATH", help=FORCE_HELP)
    uninstall.set_defaults(func=run_uninstall)
