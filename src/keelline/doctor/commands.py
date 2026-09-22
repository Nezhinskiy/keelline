"""The `doctor` command (§5.2): report an installation, and exit non-zero when one is broken.

One command and not a group, the shape §5.2's contract row states and the shape the skill
already invokes.

**A `skip` is not a finding.** Two of the sixteen checks cannot be answered by this build —
the Codex hook-trust hash §10 lists as unmeasured, and a `[ci] ref` that no repository has
recorded yet — so an exit code that counted skips would make `doctor` red on every correct
installation. `files` was the third of the two until the release lane shipped the
record it compares against. Exit 1 is reserved for `red` (C5: findings), and `warn` does not
reach it either: a budget lowered below the preset and a harness link the trust gate has not
opened are both correct states somebody should still see.

**Two is the floor and not the count.** Eight more rows have a skip arm that fires on a state of
the machine rather than on this build — `wrapper` and `files` when no plugin root can be vouched
for, `files` again on a build that carries no release record, `attached` with no overlay recorded
or an overlay that could not be asked, `pre-commit` and `overlay-requires` with no overlay root
recorded — and again, each, with a root recorded that is not a directory — `overlay-requires`
once more with no requirement declared, `bundles` and
`store-debris` with a store that does not resolve, `diagnostics` with no harness data root — and
`run_checks` skips fifteen at once when `keelline.toml` is missing or will not load. Sixteen skip
arms in all, and **seven of them carry a remedy** — but not because they skip on a state: five state
skips (`bundles`, `pre-commit`, `overlay-requires`, `store-debris`, `diagnostics`) carry nothing,
and `pre-commit`'s state is changed by the very command `checks._uncorroborated` names. The line is
whether the skip is **itself worth acting on**, and `checks.Check`'s docstring is where that rule
is stated. The plugin-root pair is the case that makes it: it is the state in which every hook
entry on the machine is silent, nothing else in the report says so, and it reports as two quiet
`skip` rows — so both carry `checks.PLUGIN_ROOT_REMEDY`.

**The remedies live in `--json` and never in the summary.** §5.2 gives every command one line,
and sixteen remedies do not fit in one; the skill relays each remedy verbatim from the report,
so a remedy absent from `--json` is a remedy the user never sees. The summary renders through
`findings.listed`, which caps at `LISTED_LIMIT` — an unbounded list of sixteen names pushes the
repairing command off the end of the line, which is the defect that constant exists for.

**`--machine` is not gated behind an interactive shell here**, unlike `attach`/`detach`'s. That
gate is about a flag deciding which overlay a *write* trusts (DP3); `doctor` writes nothing, and
gating it would make the report unable to answer about the machine file a caller just named.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.command import HOME_HELP, common_flags
from keelline.doctor.checks import RED, SKIP, WARN, Check, run_checks
from keelline.findings import listed
from keelline.result import Result


def summarise(checks: list[Check]) -> str:
    """One line: the counts, and the names of whichever status most needs reading.

    Red first, then warn, and nothing when neither: a reader who has sixteen green rows does
    not need sixteen names to say so, and a reader who has one red does not need the warnings
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
    doctor.add_argument("--home", default=None, help=HOME_HELP)
    doctor.set_defaults(func=run_doctor)
