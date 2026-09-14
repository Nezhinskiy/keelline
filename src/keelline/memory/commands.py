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
from keelline.memory.index import (
    INDEX_NAME,
    IndexCheck,
    Reconciliation,
    check_index,
    reconcile,
    render_index,
    write_index,
)
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
# `index._harvestable` refused to persist repository-authored titles into notes that are not
# themselves repository data. Said out loud because the alternative is a silent drop: the notes
# keep their own descriptions and nothing else in the output would differ.
_NOT_HARVESTED = (
    "{names} took no index line from {index}: it is committed to this repository and they are "
    "not, so its text was not written into memory the machine owns"
)
# `index._publishable` refused to write a repository-authored line into {index} because this
# run's destination reaches outside this project's own repository — the write-side mirror of
# `_NOT_HARVESTED`, said out loud for the same reason: a drop `render_index` makes on its own
# has no channel back to a person running the command, and a silent one is how repository text
# reaches every other project sharing that destination.
_NOT_PUBLISHED = (
    "{names} took no line in {index}: committed to this repository, while this run's "
    "destination reaches outside it, so none of it was published into memory the machine shares"
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


def _harvest(reconciled: Reconciliation, store: Store) -> str | None:
    """What `index._harvestable` declined to persist, named where a person will read it."""
    if not reconciled.refused_harvest:
        return None
    names = ", ".join(reconciled.refused_harvest)
    return _NOT_HARVESTED.format(names=names, index=store.path / INDEX_NAME)


def _publish(reconciled: Reconciliation, store: Store) -> str | None:
    """What `index._publishable` declined to write, named where a person will read it."""
    if not reconciled.refused_publish:
        return None
    names = ", ".join(reconciled.refused_publish)
    return _NOT_PUBLISHED.format(names=names, index=store.path / INDEX_NAME)


# A note the store holds and cannot parse is the one failure this store cannot recover from by
# itself: `walk` quarantines it so one bad file does not cost the whole store, and from there
# it is invisible to routing, to the standing rules and to volatile injection. It reached
# `Result.data` and nothing a person reads.
_UNREADABLE_NOTES = (
    "{count} file(s) in the store cannot be read as a note, so they reach neither the index "
    "nor any injection bundle: {paths}"
)


def _findings(report: IndexCheck, config: Config) -> list[str]:
    """Everything `memory index` must both say out loud and exit non-zero for.

    One list, read by the summary and by the exit code, because the two disagreed: the summary
    branched on `drifted` alone while the exit code was `drifted or over_budget`, so a run
    printed "index is current: N words, M lines" and exited 1 in the same breath. `over_caps` —
    the two limits at which the harness truncates `MEMORY.md` — was computed by `check_index`
    and then dropped entirely, absent from the data, the summary and the exit code alike.

    Drift is deliberately not here. It is the one finding whose meaning differs between the two
    callers: `--check` reports it, and the write path has just removed it.
    """
    found: list[str] = []
    if report.over_budget:
        budget = config.budgets.effective("memory_index_words")
        found.append(f"the index is {report.words} words, over its {budget}-word budget")
    if report.over_caps:
        found.append(
            f"the index is past the harness caps it is truncated at "
            f"({', '.join(report.over_caps)}): {report.lines} lines, {report.bytes_} bytes"
        )
    if report.unreadable:
        found.append(
            _UNREADABLE_NOTES.format(
                count=len(report.unreadable), paths=", ".join(report.unreadable)
            )
        )
    return found


def run_index(args: argparse.Namespace) -> Result:
    store, config = _store(args)
    machine = _machine(args)
    # Taken before anything is written, so it records the bytes the owner actually approved.
    before = trust.snapshot(store, config, machine=machine)
    reconciled = reconcile(store, config, write=not args.check, machine=machine)
    report = check_index(store, config, reconciled, machine=machine)
    findings = _findings(report, config)
    if args.check:
        if report.drifted:
            findings.insert(0, "the index is out of date; run `keelline memory index`")
        summary = (
            "; ".join(findings)
            if findings
            else f"index is current: {report.words} words, {report.lines} lines"
        )
        summary = _with(_with(summary, _harvest(reconciled, store)), _publish(reconciled, store))
        return Result(
            _with(summary, _gate(store, config, machine)),
            {
                "drifted": report.drifted,
                "words": report.words,
                "lines": report.lines,
                "bytes": report.bytes_,
                "over_budget": report.over_budget,
                "over_caps": report.over_caps,
                "provisional": report.provisional,
                "refused_harvest": reconciled.refused_harvest,
                "refused_publish": reconciled.refused_publish,
                "unreadable": report.unreadable,
                "trusted": trust.may_inject(store, config, machine=machine),
            },
            # The same list the summary is built from, so the two can no longer disagree.
            exit_code=1 if findings else 0,
        )
    text = render_index(reconciled, config, store, machine=machine)
    path = write_index(store, config, text, machine=machine)
    carried = trust.refresh_if_trusted(
        store, config, before, [*reconciled.written, path], machine=machine
    )
    note = _DROPPED if before.trusted and not carried else _gate(store, config, machine)
    # Exit 0: the write succeeded, and `--check` is the mode that fails a build. The findings
    # are still said, because a person running this by hand is who can act on them.
    wrote = "; ".join(
        [f"wrote {path} ({report.words} words, {len(reconciled.notes)} notes)", *findings]
    )
    wrote = _with(_with(wrote, _harvest(reconciled, store)), _publish(reconciled, store))
    return Result(
        _with(wrote, note),
        {
            "path": str(path),
            "words": report.words,
            "lines": report.lines,
            "harvested": reconciled.harvested,
            "provisional": reconciled.provisional,
            "refused_harvest": reconciled.refused_harvest,
            "refused_publish": reconciled.refused_publish,
            "unreadable": report.unreadable,
            "over_budget": report.over_budget,
            "over_caps": report.over_caps,
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
