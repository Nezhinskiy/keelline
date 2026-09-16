"""The `bugs` group (§5.2): `new`, `index [--check]`, `check`, `renumber OLD NEW`."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from keelline import fsops
from keelline.areas import SubParsers
from keelline.command import common_flags, root_and_config
from keelline.findings import labels, listed
from keelline.ledger.entries import SEVERITIES
from keelline.result import Result

_OK = "OK: bug ledger entries, index freshness, and identifier references"
_INERT = "nothing to check: no ledger directory and no generated index"


def run_bugs_index(args: argparse.Namespace) -> Result:
    from keelline.ledger.entries import load_entries
    from keelline.ledger.index import index_text, refuse_index_overwrite, render_index

    root, config = root_and_config(args)
    current = index_text(root, config)
    refuse_index_overwrite(root, config, current)
    entries = load_entries(root, config)
    rendered = render_index(entries, config)
    index = config.paths.bug_index
    if args.check:
        if current != rendered:
            return Result(
                f"{index} is stale; run: keelline bugs index", {"stale": True}, exit_code=1
            )
        return Result(f"OK: {index} is current ({len(entries)} entries)", {"stale": False})
    if current == rendered:
        return Result(
            f"{index} is current ({len(entries)} entries)",
            {"written": False, "entries": len(entries)},
        )
    fsops.write_within(root, index, rendered)
    return Result(
        f"rewrote {index} ({len(entries)} entries)", {"written": True, "entries": len(entries)}
    )


def run_bugs_check(args: argparse.Namespace) -> Result:
    from keelline.ledger.check import problems, uninitialised

    root, config = root_and_config(args)
    if uninitialised(root, config):
        return Result(_INERT, {"checked": False, "problems": []})
    found = problems(root, config)
    data = {"checked": True, "problems": [asdict(p) for p in found]}
    if not found:
        return Result(_OK, data)
    # Labels only on the line: a path, a line number and a rule are this lane's; the detail may
    # quote the repository and stays in `data`.
    return Result(f"FAIL: {len(found)} ledger problem(s): {labels(found)}", data, exit_code=1)


def run_bugs_new(args: argparse.Namespace) -> Result:
    from keelline.ledger.write import file_entry

    root, config = root_and_config(args)
    filed = file_entry(
        root,
        config,
        title=args.title,
        severity=args.severity,
        area=args.area,
        source=args.source,
        related=tuple(args.related),
        fetch=not args.no_fetch,
    )
    relative = filed.path.relative_to(root).as_posix()
    summary = f"filed {relative}" + (f"; {filed.warning}" if filed.warning else "")
    return Result(summary, {"id": filed.identifier, "path": relative, "warning": filed.warning})


def run_bugs_renumber(args: argparse.Namespace) -> Result:
    from keelline.ledger.write import renumber

    root, config = root_and_config(args)
    result = renumber(root, config, args.old, args.new)
    void = result.void.relative_to(root).as_posix()
    data = {"old": args.old, "new": args.new, "void": void, "unswept": result.unswept}
    if result.unswept:
        return Result(
            f"FAIL: {args.old} moved to {args.new}, but {len(result.unswept)} file(s) still "
            f"reference {args.old} and must be fixed by hand "
            f"({listed([u.split(':', 1)[0] for u in result.unswept])}); "
            f"a void pointer remains at {void}",
            data,
            exit_code=1,
        )
    return Result(f"{args.old} -> {args.new}; a void pointer remains at {void}", data)


def register(groups: SubParsers) -> None:
    bugs = groups.add_parser("bugs", help="the bug ledger")
    sub = bugs.add_subparsers(dest="command", metavar="<command>")
    new = common_flags(sub.add_parser("new", help="file a new entry and regenerate the index"))
    new.add_argument("title")
    new.add_argument("--severity", required=True, choices=SEVERITIES)
    new.add_argument("--area", required=True)
    new.add_argument("--source", default="")
    new.add_argument("--related", nargs="*", default=[])
    new.add_argument("--no-fetch", action="store_true", help="skip the pre-allocation fetch")
    new.set_defaults(func=run_bugs_new)
    index = common_flags(sub.add_parser("index", help="regenerate the index from the entry files"))
    index.add_argument("--check", action="store_true", help="fail if the index is stale")
    index.set_defaults(func=run_bugs_index)
    check = common_flags(
        sub.add_parser("check", help="validate the ledger, the index and every reference")
    )
    check.set_defaults(func=run_bugs_check)
    renumber = common_flags(sub.add_parser("renumber", help="move an entry to a free identifier"))
    renumber.add_argument("old")
    renumber.add_argument("new")
    renumber.set_defaults(func=run_bugs_renumber)
