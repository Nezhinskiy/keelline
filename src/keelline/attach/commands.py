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

    root, store, machine = _target(args)
    if args.check:
        return check(root, store=store, machine=machine)
    raise Refusal(
        "`keelline attach` writes nothing yet; run it with --check, which reports the binding "
        "and the permission diff"
    )


def run_detach(args: argparse.Namespace) -> Result:
    del args
    raise Refusal("`keelline detach` is not wired up yet")


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
