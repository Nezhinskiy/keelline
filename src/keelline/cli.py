"""The CLI frame (contract C5): one parser, areas discovered by name, three exit codes."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from typing import Any

import keelline
from keelline.areas import Registrar, SubParsers, area_modules
from keelline.errors import Failure, Refusal
from keelline.hooks.policy import hook_event_name, refuses_on_internal_error
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


def _emit(outcome: Any, as_json: bool) -> int:
    """Turn what a command returned into output and an exit code.

    Called from inside `run`'s `try`. A `Path`, `datetime`, `set` or `Decimal` in `Result.data`
    is an easy thing for a later area to write, and the plain-text path prints only `summary`
    and never notices — so the machine-readable path, the one CI consumes, is the only one that
    breaks, and it must refuse rather than report an internal error as findings.
    """
    if not isinstance(outcome, Result):
        return int(outcome)
    if as_json:
        print(json.dumps({"summary": outcome.summary, **outcome.data}, indent=2, sort_keys=True))
    else:
        print(outcome.summary)
    return outcome.exit_code


def run(argv: list[str] | None, *, parser: argparse.ArgumentParser) -> int:
    """Execute an already-built parser. Building it is `main`'s, so one judge owns that failure.

    An area's `register()` is called while the parser is built, and a broken one is the same
    class of failure as an area that raises at import — `_discovery_failed` judges both.
    """
    raw = list(sys.argv[1:] if argv is None else argv)
    args_in, as_json = split_json_flag(raw)
    args = parser.parse_args(args_in)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        return _emit(func(args), as_json)
    except Refusal as exc:
        return _report("refused", str(exc), 2, as_json)
    except Failure as exc:
        return _report("failed", str(exc), 1, as_json)
    except BaseException as exc:  # exit 1 is for findings; a bug or a Ctrl-C is not one
        return _report("internal error", f"{type(exc).__name__}: {exc}", 2, as_json)


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    try:
        registrars = discover_registrars()
        parser = build_parser(registrars)
    except BaseException as exc:  # a broken area must never read as findings, nor escape judging
        return _discovery_failed(raw, exc)
    return run(raw, parser=parser)


def _discovery_failed(raw: list[str], exc: BaseException) -> int:
    """Discovery and the parser build both abort before argparse, so `hook`'s own policy is
    applied here (§5.3).

    Exit 2 on `UserPromptSubmit` erases what the user typed, so one later area's bug in its
    `commands.py` — raised at import, or from the `register()` the parser build calls, or as
    two areas claiming one group name — must not cost the user their prompt: on a hook
    invocation the failure degrades open everywhere exit 2 does not block, and refuses only
    where it does.
    """
    reason = f"keelline: internal error: {type(exc).__name__}: {exc}"
    event = hook_event_name(raw)
    if event is not None and not refuses_on_internal_error(event):
        print(f"{reason}; continuing open", file=sys.stderr)
        return 0
    print(reason, file=sys.stderr)
    return 2
