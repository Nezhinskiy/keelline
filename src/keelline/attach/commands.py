"""The `attach` and `detach` groups (§5.2): bind a repository to the overlay, and unbind it.

Two top-level commands and not one group with two subcommands, because that is the contract
row §5.2 states and the shape the skills already invoke.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.command import common_flags
from keelline.errors import Refusal
from keelline.result import Result

_NO_STORE = (
    "`keelline attach` needs --store, naming this project's own directory inside the overlay "
    "this machine records: <overlay>/projects/<project name>/memory"
)


def _target(args: argparse.Namespace) -> tuple[Path, Path, Path | None]:
    if args.store is None:
        raise Refusal(_NO_STORE)
    machine = Path(args.machine) if args.machine else None
    return Path(args.root).resolve(), Path(args.store), machine


def run_attach(args: argparse.Namespace) -> Result:
    from keelline.attach.permissions import check
    from keelline.attach.write import attach
    from keelline.overlay.api import subprocess_runner

    root, store, machine = _target(args)
    if args.check:
        return check(root, store=store, machine=machine)
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=args.yes,
        trust_remote=args.trust_remote,
        runner=subprocess_runner(),
    )
    data = {
        # Counts and not paths, which is the rule rather than a preference: every one of these
        # paths is built out of `paths.memory` and a `memory.groups` entry, both
        # repository-authored and neither schema-constrained, and `--json` puts `data` in front
        # of the model. `keelline.memory.hooks` reports the same value the same way.
        "links_created": len(attached.links.created),
        "links_revoked": len(attached.links.revoked),
        "settings_written": attached.settings_written,
        "rules_written": list(attached.rules_written),
        "binding_recorded": attached.binding_recorded,
        "ignored": attached.ignored,
        "notes": list(attached.notes),
    }
    summary = "; ".join(
        (
            f"attached: {len(attached.links.created)} link(s), "
            f"{len(attached.rules_written)} Codex rule file(s)",
            "settings merged" if attached.settings_written else "settings unchanged",
            "binding recorded" if attached.binding_recorded else "binding already recorded",
            *attached.notes,
        )
    )
    return Result(summary, data)


def run_detach(args: argparse.Namespace) -> Result:
    from keelline.attach.write import detach

    machine = Path(args.machine) if args.machine else None
    removed = detach(Path(args.root).resolve(), machine=machine)
    data = {
        "allow_removed": list(removed.allow_removed),
        "entries_removed": list(removed.entries_removed),
        "rules_removed": list(removed.rules_removed),
        "settings_keys_removed": list(removed.settings_keys_removed),
        "ignore_region_removed": removed.ignore_region_removed,
        # A count, for the reason `run_attach` gives above.
        "links_revoked": len(removed.links.revoked),
    }
    return Result(
        f"detached: {len(removed.allow_removed)} allow rule(s), "
        f"{len(removed.entries_removed)} hook entr(ies), "
        f"{len(removed.rules_removed)} Codex rule file(s), "
        f"{len(removed.links.revoked)} link(s); the binding record was left in place",
        data,
    )


def register(groups: SubParsers) -> None:
    attach = common_flags(
        groups.add_parser("attach", help="bind this repository to the overlay and link its notes"),
        store=True,
    )
    attach.add_argument(
        "--check", action="store_true", help="report the binding and the diff, and write nothing"
    )
    attach.add_argument(
        "--trust-remote",
        action="store_true",
        help="record this repository's remote even though the overlay recorded another",
    )
    # A parameter and not a sentence in a document: in this harness the CLI is driven by a
    # model that has read repository text, so a gate enforced by model compliance is not a
    # gate (DP3). The skill's "relay the diff, then ask" is the UX around this flag.
    attach.add_argument(
        "--yes",
        action="store_true",
        help="confirm a diff that would widen a permission; refused without it",
    )
    attach.set_defaults(func=run_attach)

    detach = common_flags(
        groups.add_parser("detach", help="remove what attach added, and leave the binding")
    )
    detach.set_defaults(func=run_detach)
