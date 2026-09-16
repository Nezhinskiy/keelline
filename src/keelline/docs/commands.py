"""The `docs` and `plan` groups (§5.2)."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from keelline import fsops
from keelline.areas import SubParsers
from keelline.command import common_flags, root_and_config
from keelline.findings import labels
from keelline.result import Result

if TYPE_CHECKING:
    from keelline.config.schema import Config
    from keelline.findings import Finding

_OK = "OK: documentation budgets and link targets"
_PLAN_OK = (
    "OK: linted {n} plan(s) — references resolve, steps are non-leading, mutation outcomes are "
    "expectations, Scope/Premise are present"
)


def _graph_notices(args: argparse.Namespace, root: Path, config: Config) -> list[Finding]:
    from keelline.docs.graph import check_memory_graph
    from keelline.memory.api import resolve

    machine = Path(args.machine) if args.machine else None
    store = resolve(root, config, override=args.store, machine=machine)
    return check_memory_graph(store, config) if store is not None else []


def run_docs_check(args: argparse.Namespace) -> Result:
    from keelline.docs.hygiene import check_budgets, check_links

    root, config = root_and_config(args)
    # No flag runs exactly the enforced set the success line names; the store is resolved only
    # on `--memory-graph` (Premise 11) — advice this command does not gate on is not fetched by
    # default.
    enforced = not (args.budgets or args.links)
    problems: list[Finding] = []
    if enforced or args.budgets:
        problems.extend(check_budgets(root, config))
    if enforced or args.links:
        problems.extend(check_links(root, config))
    notices = _graph_notices(args, root, config) if args.memory_graph else []
    data = {"findings": [asdict(p) for p in problems], "notices": [asdict(n) for n in notices]}
    if problems:
        return Result(
            f"FAIL: {len(problems)} documentation problem(s): {labels(problems)}",
            data,
            exit_code=1,
        )
    # The success line names the enforced set alone. Naming the graph here once made an exit-0
    # line vouch for a graph the run had just reported broken.
    verdict = _OK
    if notices:
        verdict += (
            f" — {len(notices)} advisory NOTE(s) are unresolved and do not gate; this line does "
            "not vouch for the memory store"
        )
    return Result(verdict, data)


def run_docs_trail(args: argparse.Namespace) -> Result:
    from keelline.config.paths import contained
    from keelline.docs.hygiene import read_document
    from keelline.docs.trail import read_trail, rebuild, trail_path, undeclared_new_documents

    root, config = root_and_config(args)
    roadmap = contained(root, config.paths.roadmap)
    if not roadmap.is_file():
        return Result(f"{config.paths.roadmap} does not exist", {"stale": None}, exit_code=1)
    trail = read_trail(trail_path(root, config))
    current = read_document(roadmap, config.paths.roadmap)
    updated = rebuild(current, root, config, trail)
    if args.check:
        if current != updated:
            return Result(
                f"{config.paths.roadmap} trail listing is stale; run: keelline docs trail",
                {"stale": True},
                exit_code=1,
            )
        return Result(f"OK: {config.paths.roadmap} trail listing is current", {"stale": False})
    written = current != updated
    if written:
        fsops.write_within(root, config.paths.roadmap, updated)
    # After the write, so the listing is never left stale by this report.
    undeclared = undeclared_new_documents(current, updated, trail)
    data = {"written": written, "undeclared": undeclared}
    summary = (
        f"rewrote {config.paths.roadmap}"
        if written
        else f"{config.paths.roadmap} trail listing is current"
    )
    if undeclared:
        return Result(
            f"{summary}; {len(undeclared)} document(s) entered the trail with no declared state "
            f"and were listed as delivered — add each to trail.toml and re-run: "
            f"{', '.join(undeclared)}",
            data,
            exit_code=1,
        )
    return Result(summary, data)


def run_plan_check(args: argparse.Namespace) -> Result:
    from keelline.docs.plans import lint

    root, config = root_and_config(args)
    result = lint(root, config, plans=[Path(p).resolve() for p in args.paths], base=args.base)
    linted = [p.relative_to(root).as_posix() for p in result.linted]
    unlinted = [p.relative_to(root).as_posix() for p in result.unlinted]
    data = {
        "findings": [asdict(f) for f in result.findings],
        "linted": linted,
        "unlinted": unlinted,
    }
    if result.findings:
        return Result(
            f"FAIL: {len(result.findings)} plan problem(s): {labels(result.findings)}",
            data,
            exit_code=1,
        )
    summary = _PLAN_OK.format(n=len(linted))
    if unlinted:
        summary += f"; {len(unlinted)} uncommitted plan(s) not linted — name them as PATH arguments"
    return Result(summary, data)


def register(groups: SubParsers) -> None:
    docs = groups.add_parser("docs", help="documentation budgets, links and the design trail")
    docs_sub = docs.add_subparsers(dest="command", metavar="<command>")
    check = common_flags(
        docs_sub.add_parser("check", help="budgets and link targets; the memory graph as advice"),
        store=True,
    )
    check.add_argument("--budgets", action="store_true")
    check.add_argument("--links", action="store_true")
    check.add_argument(
        "--memory-graph", action="store_true", help="also report the store's link graph (advisory)"
    )
    check.set_defaults(func=run_docs_check)
    trail = common_flags(
        docs_sub.add_parser("trail", help="regenerate the design-and-plan trail in the roadmap")
    )
    trail.add_argument("--check", action="store_true", help="fail if the listing is stale")
    trail.set_defaults(func=run_docs_trail)

    plan = groups.add_parser("plan", help="implementation-plan lint")
    plan_sub = plan.add_subparsers(dest="command", metavar="<command>")
    lint = common_flags(
        plan_sub.add_parser("check", help="lint the plans a change touches, or the named ones")
    )
    lint.add_argument(
        "--base", default=None, help="base ref (default: origin/<project.base_branch>)"
    )
    lint.add_argument("paths", nargs="*", help="plans to lint instead of the diff")
    lint.set_defaults(func=run_plan_check)
