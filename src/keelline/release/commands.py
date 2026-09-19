from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.command import ROOT_HELP
from keelline.errors import Failure
from keelline.release.versions import check, collect
from keelline.result import Result


def run_check(args: argparse.Namespace) -> Result:
    root = Path(args.root)
    problems = check(root)
    if problems:
        raise Failure("version drift: " + "; ".join(problems))
    versions = collect(root)
    return Result(f"one version everywhere: {versions['pyproject.toml']}", {"versions": versions})


def register(groups: SubParsers) -> None:
    group = groups.add_parser("release", help="release discipline for the Keelline repository")
    sub = group.add_subparsers(dest="command", metavar="<command>")
    cmd = sub.add_parser("check", help="every version string agrees")
    cmd.add_argument("--root", default=".", help=ROOT_HELP)
    cmd.set_defaults(func=run_check)
