"""The assess area's commands: `keelline assess` runs every configured gate and the inventory's
probes over the repository as it is, writes the inventory, and prints counts; `keelline gate`
judges a change's `keelline.toml` against its base's and runs the gates as that judgement says;
`keelline adopt begin` and `keelline adopt promote` move a project's gates from advisory to
enforcing, one at a time, as each passes.

Every module a handler needs is imported inside it, so discovering this area imports neither the
gates nor the presets.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from keelline.areas import SubParsers
from keelline.command import common_flags, root_and_config
from keelline.result import Result

if TYPE_CHECKING:
    from keelline.assess.state import Transition

ASSESS_HELP = (
    "every configured gate and the inventory: what stands between this repository and enforcement"
)
BASE_HELP = (
    "the revision the plan and commit gates compare against; "
    "default refs/remotes/origin/<project.base_branch>"
)
GATE_HELP = "judge this change against the base's keelline.toml, then run the gates as it says"
BASE_REF_HELP = (
    "the base to compare against: a 40-character commit id or a refs/ name; "
    "default refs/remotes/origin/<project.base_branch>"
)
ONLY_HELP = "run only this gate, or `config` for the configuration check alone; repeat for several"
WORKFLOW_SHA_HELP = (
    "the commit of the reusable workflow running, which the workflow passes from the platform; "
    "an upgrade's [ci] ref is admitted only when it equals this"
)
ANNOTATE_HELP = "also print each finding as a GitHub workflow command, capped per level"
SUMMARY_HELP = "append the summary as markdown to this file, as a job summary"
BUILTIN_HELP = (
    "the configuration check and the built-in gates only: no command from [gates.custom] runs"
)
CUSTOM_HELP = "the gates from [gates.custom] only, with no configuration check"
NO_TREE_CONFIG = (
    "this tree has no keelline.toml at the project root, so nothing says which gates run; "
    "the run fails rather than pass a change it cannot judge"
)
NOTHING_TO_RUN = "nothing to run: no configured gate of the kind asked for"
ADOPT_HELP = "the adoption state machine: begin with a plan, then promote gates as they pass"
BEGIN_HELP = "check an adoption plan and mark an initialised project adopting"
PLAN_HELP = (
    "a markdown file directly under [paths] plans, with keelline as a word of its name; "
    "a relative path is read from the current directory"
)
PROMOTE_HELP = "enforce the named gates if all pass now; with none named, each gate that passes"
GATES_HELP = "configured gate names (default: every gate not yet enforcing)"
BEGUN = (
    "adopting: the plan passes plan check, and every gate stays advisory until "
    "`keelline adopt promote` enforces it"
)
KEPT = "the plan passes plan check; the state stays {after}"
ONLY_UNKNOWN = (
    "--only names {count} gate(s) the configuration this run uses does not have; `config` is "
    "the configuration check, and every other name is a gate from [gates]"
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


def base_ref(value: str) -> str:
    """`--base` for a command that reads the base's `keelline.toml`: refused at the parser
    unless it is a full commit id or a full `refs/` name, before anything runs."""
    from keelline.assess.rule import BASE_REF, BASE_SHAPE

    if not BASE_REF.match(value):
        raise argparse.ArgumentTypeError(BASE_SHAPE)
    return value


def run_gate(args: argparse.Namespace) -> Result:
    from keelline import __version__
    from keelline.assess import rule
    from keelline.assess.gates import GateContext, run_gates
    from keelline.assess.report import GateRun, config_line, summary, workflow_commands
    from keelline.config.loader import ConfigError, loads, read_document
    from keelline.config.schema import CONFIG_CHECK
    from keelline.errors import Refusal
    from keelline.release.api import is_released
    from keelline.runner import subprocess_runner

    root = Path(args.root).absolute()
    prefix = rule.repository_prefix(root)
    machine = Path(args.machine) if args.machine else None
    tree_text = read_document(root)
    if tree_text is None:
        raise ConfigError(NO_TREE_CONFIG)
    # The tree's configuration is read here for its default base alone and kept nowhere: every
    # later decision is the verdict's, and a name for the tree's copy in scope is one a later
    # line could pick in its place.
    default = rule.local_base(loads(tree_text, root, machine=machine, interactive=False))
    base = args.base or default
    runner = subprocess_runner()
    verdict = rule.judge(
        root,
        rule.read_base(root, base),
        tree_text,
        machine=machine,
        running=__version__,
        workflow_sha=args.workflow_sha,
        released=lambda sha: is_released(sha, runner, cwd=root),
    )
    # The configuration this run uses is the verdict's: the base's when anything was refused, so
    # the names it runs, which of them are custom, and the paths and commands the gates read are
    # all the base's then. `enforcing` is both sides', so it can name a gate only the refused
    # tree defines; that gate is not run, and the refusal already fails the run.
    configured = verdict.config.gate_names
    only = tuple(dict.fromkeys(args.only or (CONFIG_CHECK, *configured)))
    stray = [name for name in only if name != CONFIG_CHECK and name not in configured]
    if stray:
        # Counted, never echoed: the names come from the caller workflow, which the pull request
        # can edit.
        raise Refusal(ONLY_UNKNOWN.format(count=len(stray)))
    # The workflow's two steps: the one that judges runs no command the repository wrote, and
    # the custom gates run in the next, after it passed. A name of the other kind is that
    # step's to run, so it is skipped here and not refused.
    custom = verdict.config.gates.custom
    if args.part == "builtin":
        only = tuple(name for name in only if name not in custom)
    elif args.part == "custom":
        only = tuple(name for name in only if name in custom)
    results = run_gates(
        GateContext(root, verdict.config, base), [n for n in only if n != CONFIG_CHECK]
    )
    gate_run = GateRun(verdict, results, judged=CONFIG_CHECK in only, prefix=prefix)
    lines = [config_line(verdict)] if gate_run.judged else []
    for result in results:
        mode = "enforcing" if result.name in verdict.enforcing else "advisory"
        count = f"{len(result.findings)} finding(s)" if result.answered else "could not run"
        lines.append(f"{result.name}: {mode}, {count}")
    data = {
        "config": {
            "judged": gate_run.judged,
            "base_state": verdict.base_state,
            "changes": [{"key": c.key, "verdict": c.verdict.value} for c in verdict.changes],
            "refused": verdict.refused,
            "enforcing": sorted(verdict.enforcing),
        },
        "gates": [
            {
                "name": r.name,
                "enforcing": r.name in verdict.enforcing,
                "answered": r.answered,
                "count": len(r.findings),
            }
            for r in results
        ],
    }
    if not lines:
        # Not a refusal: the workflow runs `--custom` on every caller, most of which have no
        # gate of their own.
        return Result(NOTHING_TO_RUN, data, exit_code=0)
    if args.summary:
        # The command's one write. The path is argv: in CI the platform's job summary, which
        # Keelline's own workflow passes, and locally a path a person typed; no value in the
        # repository chooses it.
        with Path(args.summary).open("a", encoding="utf-8") as stream:
            stream.write(summary(gate_run))
    if args.annotate:
        lines += workflow_commands(gate_run)
    return Result("\n".join(lines), data, exit_code=gate_run.exit_code)


def _transition(transition: Transition) -> dict[str, object]:
    """`--json` for `adopt promote`: the state before and after, and what each gate came to."""
    return {
        "before": transition.before,
        "after": transition.after,
        "promoted": list(transition.promoted),
        "failing": dict(transition.failing),
        "unanswered": list(transition.unanswered),
    }


def run_adopt_begin(args: argparse.Namespace) -> Result:
    from keelline.assess.state import begin

    root, config = root_and_config(args)
    transition = begin(root, config, Path(args.plan))
    changed = transition.after != transition.before
    summary = BEGUN if changed else KEPT.format(after=transition.after)
    # The state on each side and nothing else: `begin` runs no gate.
    return Result(summary, {"before": transition.before, "after": transition.after})


def run_adopt_promote(args: argparse.Namespace) -> Result:
    from keelline.assess.rule import local_base
    from keelline.assess.state import promote

    root, config = root_and_config(args)
    transition = promote(root, config, args.gates, base=args.base or local_base(config))
    # Gate names only: the loader holds each to a grammar, and a count is Keelline's own.
    advisory = [f"{name} ({count} finding(s))" for name, count in transition.failing.items()]
    advisory += [f"{name} (could not run)" for name in transition.unanswered]
    parts = [f"promoted: {', '.join(transition.promoted) or 'nothing'}"]
    if advisory:
        parts.append(f"still advisory: {', '.join(advisory)}")
    parts.append(f"state {transition.after}")
    data = _transition(transition)
    return Result("; ".join(parts), data, exit_code=1 if advisory else 0)


def register(groups: SubParsers) -> None:
    parser = common_flags(groups.add_parser("assess", help=ASSESS_HELP))
    parser.add_argument("--base", default=None, help=BASE_HELP)
    parser.set_defaults(func=run_assess)

    gate = common_flags(groups.add_parser("gate", help=GATE_HELP))
    gate.add_argument("--only", action="append", default=None, metavar="NAME", help=ONLY_HELP)
    gate.add_argument("--base", default=None, type=base_ref, help=BASE_REF_HELP)
    part = gate.add_mutually_exclusive_group()
    part.add_argument(
        "--builtin", dest="part", action="store_const", const="builtin", help=BUILTIN_HELP
    )
    part.add_argument(
        "--custom", dest="part", action="store_const", const="custom", help=CUSTOM_HELP
    )
    gate.add_argument("--workflow-sha", default=None, metavar="SHA", help=WORKFLOW_SHA_HELP)
    gate.add_argument("--annotate", action="store_true", help=ANNOTATE_HELP)
    gate.add_argument("--summary", default=None, metavar="FILE", help=SUMMARY_HELP)
    gate.set_defaults(func=run_gate)

    adopt = groups.add_parser("adopt", help=ADOPT_HELP)
    adopt_sub = adopt.add_subparsers(dest="command", metavar="<command>")
    start = common_flags(adopt_sub.add_parser("begin", help=BEGIN_HELP))
    start.add_argument("plan", metavar="PLAN", help=PLAN_HELP)
    start.set_defaults(func=run_adopt_begin)
    promotion = common_flags(adopt_sub.add_parser("promote", help=PROMOTE_HELP))
    promotion.add_argument("gates", nargs="*", metavar="GATE", help=GATES_HELP)
    promotion.add_argument("--base", default=None, type=base_ref, help=BASE_REF_HELP)
    promotion.set_defaults(func=run_adopt_promote)
