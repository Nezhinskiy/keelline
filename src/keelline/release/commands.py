"""The `release` group (§5.2): one version everywhere, the changelog, and the file record.

**`release notes --draft` is the one summary in this CLI that is not one line**, and it is
deliberate: §5.2 gives every command one line because a line is what a caller reads, and a
draft's whole purpose is that a person reads the section towncrier *would* write before it is
written. Printing it through `Result.summary` is what puts it on stdout under the same frame as
every other command, and `docs/cli.md` documents it as the rendered section. Every other
command here, `--draft` included under `--json`, keeps the one-line contract.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.command import ROOT_HELP
from keelline.errors import Failure
from keelline.release.hashes import HASHED_FILES, drift, write_record
from keelline.release.notes import build
from keelline.release.versions import check, collect
from keelline.result import Result
from keelline.runner import subprocess_runner

TAG_HELP = "the tag this run was created from; the six sources and the changelog must agree with it"
HASHES_CHECK_HELP = "report drift and write nothing"


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


def run_hashes(args: argparse.Namespace) -> Result:
    root = Path(args.root)
    if args.check:
        problems = drift(root)
        if problems:
            raise Failure("release record drift: " + "; ".join(problems))
        return Result(f"{len(HASHED_FILES)} shipped file(s) match the release record")
    write_record(root)
    return Result(f"recorded {len(HASHED_FILES)} shipped file(s)", {"files": sorted(HASHED_FILES)})


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
    hashes = sub.add_parser("hashes", help="record the shipped files' hashes for this release")
    hashes.add_argument("--check", action="store_true", help=HASHES_CHECK_HELP)
    hashes.add_argument("--root", default=".", help=ROOT_HELP)
    hashes.set_defaults(func=run_hashes)
