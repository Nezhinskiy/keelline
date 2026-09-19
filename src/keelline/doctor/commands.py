"""The `doctor` command (§5.2): report an installation, and exit non-zero when one is broken.

One command and not a group, the shape §5.2's contract row states and the shape the skill
already invokes.

**A `skip` is not a finding.** Three of the fifteen checks cannot be answered by this build —
the release's recorded hashes, the Codex hook-trust hash §10 lists as unmeasured, and a `[ci]
ref` that `init` has not shipped a writer for — so an exit code that counted skips would make
`doctor` red on every correct installation until wave 5. Exit 1 is reserved for `red` (C5:
findings), and `warn` does not reach it either: a budget lowered below the preset and a harness
link the trust gate has not opened are both correct states somebody should still see.

**Three is the floor and not the count.** Five more rows have a skip arm that fires on a state
of the machine rather than on this build — `wrapper` and a second arm of `files` when no plugin
root can be vouched for, `pre-commit` with no overlay root recorded, `bundles` and
`store-debris` with a store that does not resolve, `diagnostics` with no harness data root — and
`run_checks` skips fourteen at once when `keelline.toml` is missing or will not load. The
plugin-root pair is the one that matters: it is the state in which every hook entry on the
machine is silent, and it reports as two `skip` rows, so both carry `checks.PLUGIN_ROOT_REMEDY`
rather than the empty remedy a "this build cannot answer" skip is entitled to.

**The remedies live in `--json` and never in the summary.** §5.2 gives every command one line,
and fifteen remedies do not fit in one; the skill relays each remedy verbatim from the report,
so a remedy absent from `--json` is a remedy the user never sees. The summary renders through
`findings.listed`, which caps at `LISTED_LIMIT` — an unbounded list of fifteen names pushes the
repairing command off the end of the line, which is the defect that constant exists for.

**`--machine` is not gated behind an interactive shell here**, unlike `attach`/`detach`'s. That
gate is about a flag deciding which overlay a *write* trusts (DP3); `doctor` writes nothing, and
gating it would make the report unable to answer about the machine file a caller just named.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.command import common_flags
from keelline.doctor.checks import RED, SKIP, WARN, Check, run_checks
from keelline.findings import listed
from keelline.result import Result


def summarise(checks: list[Check]) -> str:
    """One line: the counts, and the names of whichever status most needs reading.

    Red first, then warn, and nothing when neither: a reader who has fifteen green rows does
    not need fifteen names to say so, and a reader who has one red does not need the warnings
    in front of it.
    """
    red = [check.name for check in checks if check.status == RED]
    warn = [check.name for check in checks if check.status == WARN]
    skipped = [check.name for check in checks if check.status == SKIP]
    counts = f"{len(checks)} checks: {len(red)} red, {len(warn)} warn, {len(skipped)} skipped"
    if red:
        return f"{counts}; red: {listed(red)}"
    if warn:
        return f"{counts}; warn: {listed(warn)}"
    return counts


def run_doctor(args: argparse.Namespace) -> Result:
    from keelline.runner import subprocess_runner

    root = Path(args.root).resolve()
    checks = run_checks(
        root,
        # `None` means the machine owner's own, said out loud rather than defaulted — the rule
        # every function this plan added follows, and for the reason `attach.write` gives: a
        # resolver without one reads the developer's real `~`.
        home=Path(args.home).expanduser() if args.home else None,
        machine=Path(args.machine) if args.machine else None,
        runner=subprocess_runner(),
    )
    data = {
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
                "remedy": check.remedy,
            }
            for check in checks
        ]
    }
    findings = sum(1 for check in checks if check.status == RED)
    return Result(summarise(checks), data, exit_code=1 if findings else 0)


def register(groups: SubParsers) -> None:
    doctor = common_flags(groups.add_parser("doctor", help="report on this installation"))
    doctor.add_argument(
        "--home",
        default=None,
        help="the home directory whose harness files to read (default: the real one)",
    )
    doctor.set_defaults(func=run_doctor)
