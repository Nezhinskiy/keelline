"""The `init` command (§5.2, §8.1): write a repository's Keelline footprint, once.

One command and not a group, the shape §5.2's contract row states and the shape the skill
already invokes.

**The summary is both rendered reports, the way `overlay upgrade`'s is.** It was four lines of
counts, with every artifact's verb and the whole REFUSED section reachable only under `--json`
— so the skill that tells a relayer to pass on "both reports" and "every refused line" was
describing output the command did not print, and the exit-1 path is the one a person meets
without a flag. `scaffold.render_report` is the renderer, and the same text goes into `--json`
under `once` and `footprint`, so the two cannot disagree.

That is safe on the repository-bytes rule, and the reason is `scaffold.report`'s own format
string: a line is `{verb} {target} ({reason})`, where the target is a `config.paths` value the
loader has bounded to `PATH_VALUE` plus a file name this area chose, and the reason is the
engine's own fixed vocabulary. The CI line beside them is one of this area's fixed sentences,
or a tag and a commit the *release* area resolved from the public repository's own tags. The
project's name and its `[ci]` values reach neither.

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
from pathlib import Path

from keelline.areas import SubParsers
from keelline.command import DRY_RUN_HELP, common_flags
from keelline.result import Result
from keelline.scaffold import render_report

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


def register(groups: SubParsers) -> None:
    # `parser` and not `init`: the name `init` in this module is the command, and the function
    # `run_init` imports from `keelline.project.init`.
    parser = common_flags(groups.add_parser("init", help="write this repository's footprint"))
    parser.add_argument("--yes", action="store_true", help=YES_HELP)
    parser.add_argument("--dry-run", action="store_true", help=DRY_RUN_HELP)
    parser.add_argument("--no-ci", dest="ci", action="store_false", help=NO_CI_HELP)
    parser.set_defaults(func=run_init, ci=True)
