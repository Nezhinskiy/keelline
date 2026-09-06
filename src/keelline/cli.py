"""The CLI frame (contract C5): one parser, areas discovered by name, three exit codes."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import pkgutil
import sys
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import keelline
from keelline.errors import Failure, Refusal
from keelline.result import Result

if TYPE_CHECKING:
    SubParsers = argparse._SubParsersAction[argparse.ArgumentParser]
else:
    # Generic only in typeshed: subscripting the class at runtime raises TypeError.
    SubParsers = argparse._SubParsersAction

Registrar = Callable[[SubParsers], None]


def discover_registrars() -> list[Registrar]:
    """Every `keelline.<area>.commands.register`, in name order, with no shared registry."""
    registrars: list[Registrar] = []
    for module in sorted(pkgutil.iter_modules(keelline.__path__), key=lambda m: m.name):
        if not module.ispkg:
            continue
        spec = importlib.util.find_spec(f"keelline.{module.name}.commands")
        if spec is None:
            continue
        registrars.append(importlib.import_module(spec.name).register)
    return registrars


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
