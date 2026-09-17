"""The `overlay` group (§5.2): create an instance, and make it the owner's."""

from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.errors import Refusal
from keelline.result import Result

# Neither source is a default, and that is the point. §6.1 permits the GitHub path only after
# explicit confirmation, and a non-interactive caller — which in this harness is the usual one —
# can express confirmation only by naming the source. A default would turn an omitted flag into
# a repository created on somebody's account.
_NO_SOURCE = (
    "`keelline overlay create` needs one of --template (ask GitHub to generate a private "
    "repository from the template repository and clone it) or --local (render the shipped "
    "template here, touching no network). Neither is the default: say which one you want"
)


def run_overlay_create(args: argparse.Namespace) -> Result:
    from keelline.overlay.create import create
    from keelline.overlay.runner import subprocess_runner

    if args.source is None:
        raise Refusal(_NO_SOURCE)
    created = create(
        args.owner,
        args.name,
        source=args.source,
        root=Path(args.root).resolve(),
        runner=subprocess_runner(),
    )
    data = {"root": str(created.root), "source": created.source, "notes": list(created.notes)}
    return Result(f"overlay at {created.root} ({'; '.join(created.notes)})", data)


def run_overlay_init(args: argparse.Namespace) -> Result:
    from keelline.overlay.create import init_instance
    from keelline.overlay.runner import subprocess_runner

    result = init_instance(Path(args.root).resolve(), args.owner, runner=subprocess_runner())
    data = {"renamed": list(result.renamed), "notes": list(result.notes)}
    return Result("; ".join(result.notes), data)


def register(groups: SubParsers) -> None:
    overlay = groups.add_parser("overlay", help="the owner's private overlay")
    sub = overlay.add_subparsers(dest="command", metavar="<command>")

    create = sub.add_parser("create", help="create a private overlay repository, or render one")
    create.add_argument("--owner", required=True, help="the account the overlay belongs to")
    create.add_argument(
        "--name", default="keelline-private", help="the repository name (default: %(default)s)"
    )
    create.add_argument(
        "--root", default=".", help="directory to create it in (default: current directory)"
    )
    # Mutually exclusive and neither is required, so that "neither was given" reaches the
    # command as a refusal naming both rather than as argparse's own usage error.
    source = create.add_mutually_exclusive_group()
    source.add_argument(
        "--template",
        dest="source",
        action="store_const",
        const="template",
        help="generate it on GitHub from the template repository and clone it",
    )
    source.add_argument(
        "--local",
        dest="source",
        action="store_const",
        const="local",
        help="render the shipped template here; no network call is made",
    )
    create.set_defaults(func=run_overlay_create, source=None)

    init = sub.add_parser("init", help="make a created overlay this owner's")
    init.add_argument("--owner", required=True, help="the account to name this overlay after")
    init.add_argument("--root", default=".", help="the overlay root (default: current directory)")
    init.set_defaults(func=run_overlay_init)
