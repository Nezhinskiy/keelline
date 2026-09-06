"""The CLI frame (contract C5): one parser, three exit codes."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import keelline
from keelline.errors import Failure, Refusal

if TYPE_CHECKING:
    SubParsers = argparse._SubParsersAction[argparse.ArgumentParser]
else:
    # Generic only in typeshed: subscripting the class at runtime raises TypeError.
    SubParsers = argparse._SubParsersAction

Registrar = Callable[[SubParsers], None]


def build_parser(registrars: Iterable[Registrar] = ()) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="keelline", description=keelline.__doc__)
    parser.add_argument("--version", action="version", version=f"keelline {keelline.__version__}")
    groups = parser.add_subparsers(dest="group", metavar="<group>")
    for register in registrars:
        register(groups)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "func", None) is None:
        parser.print_help()
        return 2
    try:
        return int(args.func(args))
    except Refusal as exc:
        print(f"keelline: refused: {exc}", file=sys.stderr)
        return 2
    except Failure as exc:
        print(f"keelline: failed: {exc}", file=sys.stderr)
        return 1
