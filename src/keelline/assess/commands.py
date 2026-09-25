"""The assess area's command: `keelline assess` runs every configured gate and the inventory's
probes over the repository as it is, writes the inventory, and prints counts.

The assessment module is imported inside the handler, so discovering this area imports neither
the gates nor the presets.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.command import common_flags
from keelline.result import Result

ASSESS_HELP = (
    "every configured gate and the inventory: what stands between this repository and enforcement"
)
BASE_HELP = (
    "the revision the plan and commit gates compare against; "
    "default refs/remotes/origin/<project.base_branch>"
)


def run_assess(args: argparse.Namespace) -> Result:
    from keelline.assess.assessment import NOT_IGNORED, assess, document, ignored, render, write

    root = Path(args.root).resolve()
    assessment = assess(root, machine=Path(args.machine) if args.machine else None, base=args.base)
    write(root, assessment)
    summary = render(assessment)
    if ignored(root) is False:
        summary += f"\n\n{NOT_IGNORED}"
    return Result(summary, document(assessment), exit_code=1 if assessment.would_fail else 0)


def register(groups: SubParsers) -> None:
    parser = common_flags(groups.add_parser("assess", help=ASSESS_HELP))
    parser.add_argument("--base", default=None, help=BASE_HELP)
    parser.set_defaults(func=run_assess)
