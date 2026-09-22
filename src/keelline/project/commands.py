"""The `init` command (§5.2, §8.1): write a repository's Keelline footprint, once.

One command and not a group, the shape §5.2's contract row states and the shape the skill
already invokes.

**The summary is counts and Keelline's own vocabulary, and nothing else.** Both count lines
come from `scaffold.render_report`, which interpolates numbers; the CI line is one of this
area's own fixed sentences, or a tag and a commit the *release* area resolved from the public
repository's tags. The project's own name, its paths and its `[ci]` values are the repository's
bytes and stay out of the line. The two full reports — every artifact with its verb, and the
REFUSED section when there is one — are in `--json` under `once` and `footprint`, which is
where the skill relays them from.

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
from keelline.scaffold import Plan, render_report

NO_CI_HELP = 'write no CI workflow and ask no remote for a pin; sets [ci] mode = "none"'
YES_HELP = (
    "accept the detected defaults and write the footprint; without it nothing is written and "
    "the command refuses, naming the lane that ships the questions"
)


def _counts(planned: Plan) -> str:
    """The last line of the plan's own report: the six numbers, from the same renderer."""
    return render_report(planned).splitlines()[-1]


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
    pin = report.resolution.pin
    if pin is not None:
        ci_line = f"CI: {pin.tag}@{pin.sha}"
    else:
        ci_line = f"CI: skipped — {report.skipped.get('ci-workflow', 'no workflow was planned')}"
    lines = [
        "would initialise:" if report.dry_run else "initialised:",
        f"  write-once: {_counts(report.once)}",
        f"  footprint: {_counts(report.footprint)}",
        f"  {ci_line}",
    ]
    if report.note:
        lines.append(f"  note: {report.note}")
    data = {
        "dry_run": report.dry_run,
        "adopted": report.adopted,
        "once": render_report(report.once),
        "footprint": render_report(report.footprint),
        "writes": [*report.once.writes, *report.footprint.writes],
        "skipped": dict(report.skipped),
        "pin": None if pin is None else {"tag": pin.tag, "sha": pin.sha},
        "asked": report.resolution.asked,
        "note": report.note,
    }
    refused = bool(report.once.refusals or report.footprint.refusals)
    return Result("\n".join(lines), data, exit_code=1 if refused else 0)


def register(groups: SubParsers) -> None:
    init = common_flags(groups.add_parser("init", help="write this repository's footprint"))
    init.add_argument("--yes", action="store_true", help=YES_HELP)
    init.add_argument("--dry-run", action="store_true", help=DRY_RUN_HELP)
    init.add_argument("--no-ci", dest="ci", action="store_false", help=NO_CI_HELP)
    init.set_defaults(func=run_init, ci=True)
