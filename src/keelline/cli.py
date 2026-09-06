"""The CLI frame (contract C5): one parser, areas discovered by name, three exit codes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable

import keelline
from keelline.areas import Registrar, SubParsers, area_modules
from keelline.errors import Failure, Refusal
from keelline.result import Result

# The aliases live in the leaf module every area imports; they are re-exported here because
# `from keelline.cli import SubParsers` is the import an area command module already writes.
__all__ = [
    "Registrar",
    "SubParsers",
    "build_parser",
    "discover_registrars",
    "main",
    "run",
    "split_json_flag",
]


def discover_registrars() -> list[Registrar]:
    """Every `keelline.<area>.commands.register`, in name order, with no shared registry."""
    return [module.register for module in area_modules("commands")]


def build_parser(registrars: Iterable[Registrar] = ()) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="keelline", description=keelline.__doc__)
    parser.add_argument("--version", action="version", version=f"keelline {keelline.__version__}")
    groups = parser.add_subparsers(dest="group", metavar="<group>")
    for register in registrars:
        register(groups)
    return parser


def split_json_flag(argv: list[str]) -> tuple[list[str], bool]:
    """`--json` is accepted anywhere, so every command carries it without declaring it."""
    return [arg for arg in argv if arg != "--json"], "--json" in argv


def _report(kind: str, message: str, code: int, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"summary": f"{kind}: {message}", "error": kind}, sort_keys=True))
    else:
        print(f"keelline: {kind}: {message}", file=sys.stderr)
    return code


def run(argv: list[str] | None, *, registrars: Iterable[Registrar]) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    args_in, as_json = split_json_flag(raw)
    parser = build_parser(registrars)
    args = parser.parse_args(args_in)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        outcome = func(args)
    except Refusal as exc:
        return _report("refused", str(exc), 2, as_json)
    except Failure as exc:
        return _report("failed", str(exc), 1, as_json)
    if not isinstance(outcome, Result):
        return int(outcome)
    if as_json:
        print(json.dumps({"summary": outcome.summary, **outcome.data}, indent=2, sort_keys=True))
    else:
        print(outcome.summary)
    return outcome.exit_code


def main(argv: list[str] | None = None) -> int:
    try:
        registrars = discover_registrars()
    except Exception as exc:  # a broken area must never read as findings
        print(f"keelline: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return run(argv, registrars=registrars)
