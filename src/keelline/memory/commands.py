"""The `memory` group (§5.2). Every command takes `--store PATH` (§9.1).

`--store` is an override of *where the notes are*, not of the rules about them: it is held to
the same target rule as a link the resolver found, so passing a path is not a way around the
overlay binding. `--machine` exists for the same reason the resolver takes one — a test that
did not thread it would read the developer's real configuration and, worse, write a trust
record into their home directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.config.loader import load
from keelline.config.schema import Config
from keelline.errors import Failure, Refusal
from keelline.memory import trust
from keelline.memory.bundles import Bundle, fit, render
from keelline.memory.index import check_index, reconcile, render_index, write_index
from keelline.memory.inventory import inventory, totals
from keelline.memory.store import Store, refusal_reason, resolve
from keelline.result import Result


def _machine(args: argparse.Namespace) -> Path | None:
    value = getattr(args, "machine", None)
    return Path(value) if value else None


def _store(args: argparse.Namespace) -> tuple[Store, Config]:
    root = Path(args.root).resolve()
    config = load(root, machine=_machine(args))
    store = resolve(root, config, override=args.store, machine=_machine(args))
    if store is None:
        reason = refusal_reason(root, config, override=args.store, machine=_machine(args))
        raise Failure(reason or "no memory store")
    return store, config


# What `bundles.blocks` returns `[]` for, said where a person will read it. The failure this
# closes was silent in both directions: `memory index` rewrites every note and `MEMORY.md`, so
# it used to revoke the very record it depends on, and nothing in any summary said why the
# model had stopped receiving standing rules.
_UNTRUSTED = (
    "this store's notes are repository data with no trust record, so the standing-rules, "
    "volatile-notes and index bundles are empty — run `keelline memory trust --in-repo-memory`"
)
# The narrow case where a Keelline-authored write cannot carry trust forward: the store changed
# under it, so re-recording would bless bytes the owner has never looked at. `refresh_if_trusted`
# refuses rather than guess, which is right, and the human has to be told which it was.
_DROPPED = (
    "the store changed while this command ran, so its trust record was not carried over — "
    "review the change and re-run `keelline memory trust --in-repo-memory`"
)


def _gate(store: Store, config: Config, machine: Path | None) -> str | None:
    """Whether the trust gate is what a person should be told about, after a command ran.

    Deliberately not wired into `session-context`: that command's `Result.summary` *is* the
    text the `SessionStart` entry emits, so a diagnostic there would be injected into the model
    rather than read by anyone. Nor into the handler, which stays `Policy.OPEN` and quiet. The
    commands a person runs by hand are where this belongs.
    """
    return None if trust.may_inject(store, config, machine=machine) else _UNTRUSTED


def _with(summary: str, note: str | None) -> str:
    return summary if note is None else f"{summary}; {note}"


def run_index(args: argparse.Namespace) -> Result:
    store, config = _store(args)
    machine = _machine(args)
    # Taken before anything is written, so it records the bytes the owner actually approved.
    before = trust.snapshot(store, config, machine=machine)
    reconciled = reconcile(store, config, write=not args.check, machine=machine)
    report = check_index(store, config, reconciled)
    if args.check:
        summary = (
            "index is out of date; run `keelline memory index`"
            if report.drifted
            else f"index is current: {report.words} words, {report.lines} lines"
        )
        return Result(
            _with(summary, _gate(store, config, machine)),
            {
                "drifted": report.drifted,
                "words": report.words,
                "lines": report.lines,
                "over_budget": report.over_budget,
                "over_caps": report.over_caps,
                "provisional": report.provisional,
                "unreadable": report.unreadable,
                "trusted": trust.may_inject(store, config, machine=machine),
            },
            exit_code=1 if report.drifted or report.over_budget else 0,
        )
    path = write_index(store, render_index(reconciled, config, store))
    carried = trust.refresh_if_trusted(
        store, config, before, [*reconciled.written, path], machine=machine
    )
    note = _DROPPED if before.trusted and not carried else _gate(store, config, machine)
    return Result(
        _with(f"wrote {path} ({report.words} words, {len(reconciled.notes)} notes)", note),
        {
            "path": str(path),
            "words": report.words,
            "harvested": reconciled.harvested,
            "provisional": reconciled.provisional,
            "unreadable": report.unreadable,
            "over_budget": report.over_budget,
            "trusted": trust.may_inject(store, config, machine=machine),
        },
    )


def run_session_context(args: argparse.Namespace) -> Result:
    try:
        bundle = Bundle(args.bundle)
    except ValueError as exc:
        known = ", ".join(b.value for b in Bundle)
        raise Refusal(f"unknown bundle {args.bundle!r}; known: {known}") from exc
    store, config = _store(args)
    text = render(bundle, store, config, part=args.part, machine=_machine(args))
    return Result(text if text is not None else "")


def run_trust(args: argparse.Namespace) -> Result:
    store, config = _store(args)
    before = trust.state(store, config, machine=_machine(args))
    after = trust.record(store, config, machine=_machine(args))
    return Result(
        f"recorded the store hash for {store.path}",
        {"was_trusted": before.trusted, "trusted": after.trusted, "digest": after.current},
    )


def run_inventory(args: argparse.Namespace) -> Result:
    store, config = _store(args)
    reconciled = reconcile(store, config, write=False, machine=_machine(args))
    entries = inventory(reconciled, config)
    counts = totals(entries, config)
    return Result(
        f"{counts['notes']} notes, {counts['words']} words, "
        f"{counts['provisional']} provisional, {counts['stale']} stale",
        {"entries": [entry.as_dict() for entry in entries], **counts},
    )


def run_doctor_bundles(args: argparse.Namespace) -> Result:
    """What `doctor` reads: whether each bundle fits the slots `hooks.json` declares."""
    store, config = _store(args)
    report = {
        bundle.value: {
            "parts": (found := fit(bundle, store, config, machine=_machine(args))).parts,
            "slots": found.slots,
            "overflow": found.overflow,
            "oversized": found.oversized,
        }
        for bundle in Bundle
    }
    bad = [name for name, row in report.items() if row["overflow"] or row["oversized"]]
    summary = "every bundle fits its slots" if not bad else f"does not fit: {', '.join(bad)}"
    machine = _machine(args)
    # A bundle that fits because it is empty is not a bundle that fits. `doctor` reads this.
    trusted = trust.may_inject(store, config, machine=machine)
    return Result(
        _with(summary, _gate(store, config, machine)),
        {"bundles": report, "trusted": trusted},
        exit_code=1 if bad else 0,
    )


def _with_common(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    parser.add_argument("--store", default=None, help="resolve the store at this path")
    parser.add_argument("--machine", default=None, help="machine configuration file to read")
    return parser


def register(groups: SubParsers) -> None:
    group = groups.add_parser("memory", help="the working-memory store")
    sub = group.add_subparsers(dest="command", metavar="<command>")

    index = _with_common(sub.add_parser("index", help="render MEMORY.md from the notes"))
    index.add_argument("--check", action="store_true", help="report drift instead of writing")
    index.set_defaults(func=run_index)

    context = _with_common(sub.add_parser("session-context", help="render one injection bundle"))
    context.add_argument("--bundle", required=True, help=", ".join(b.value for b in Bundle))
    context.add_argument("--part", type=int, default=1, help="which numbered slot to render")
    context.set_defaults(func=run_session_context)

    trusted = _with_common(sub.add_parser("trust", help="trust notes committed to this repository"))
    trusted.add_argument(
        "--in-repo-memory",
        action="store_true",
        required=True,
        # Required and never read by `run_trust` — that is not a missing guard, it is the whole
        # point. This is an explicit-confirmation gesture, not a switch between two behaviours:
        # its presence is what stops `memory trust` from being a bare, trivially scripted
        # command. It is not a safety check either, so there is nothing here to branch on: trust
        # is only ever *consulted* for content that lives in the repository — the notes, when
        # `inside_project(store)`, and `MEMORY.md` whenever it resolves inside the repository,
        # which it does in overlay mode too, since `store.path` is a real directory there. For
        # a store holding neither, `trust.may_inject` short-circuits to `True`, so recording a
        # hash for it is inert rather than dangerous.
        help="the only kind of store trust applies to",
    )
    trusted.set_defaults(func=run_trust)

    listing = _with_common(sub.add_parser("inventory", help="what a memory sweep reads"))
    listing.set_defaults(func=run_inventory)

    fitting = _with_common(sub.add_parser("fit", help="whether each bundle fits its hook slots"))
    fitting.set_defaults(func=run_doctor_bundles)
