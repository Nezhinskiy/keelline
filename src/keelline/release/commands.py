from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.command import ROOT_HELP
from keelline.errors import Failure
from keelline.release.notes import build
from keelline.release.versions import check, collect
from keelline.result import Result
from keelline.runner import subprocess_runner

TAG_HELP = "the tag this run was created from; the six sources and the changelog must agree with it"


def run_check(args: argparse.Namespace) -> Result:
    root = Path(args.root)
    problems = check(root, tag=args.tag)
    if problems:
        raise Failure("version drift: " + "; ".join(problems))
    versions = collect(root)
    return Result(f"one version everywhere: {versions['pyproject.toml']}", {"versions": versions})


def run_notes(args: argparse.Namespace) -> Result:
    root = Path(args.root)
    rendered = build(root, version=args.version, draft=args.draft, runner=subprocess_runner())
    if args.draft:
        return Result(rendered.rstrip("\n"), {"draft": rendered})
    return Result(f"CHANGELOG.md carries {args.version}")


def register(groups: SubParsers) -> None:
    group = groups.add_parser("release", help="release discipline for the Keelline repository")
    sub = group.add_subparsers(dest="command", metavar="<command>")
    cmd = sub.add_parser("check", help="every version string agrees")
    cmd.add_argument("--root", default=".", help=ROOT_HELP)
    cmd.add_argument("--tag", default=None, help=TAG_HELP)
    cmd.set_defaults(func=run_check)
    notes = sub.add_parser("notes", help="assemble CHANGELOG.md from changelog.d through towncrier")
    notes.add_argument("--version", required=True, help="the version to assemble the section under")
    notes.add_argument("--draft", action="store_true", help="render without writing")
    notes.add_argument("--root", default=".", help=ROOT_HELP)
    notes.set_defaults(func=run_notes)
