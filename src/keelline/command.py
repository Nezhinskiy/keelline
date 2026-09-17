"""What every configured command shares: the common flags and the configuration load.

Three areas register commands that take `--root` and `--machine` and then load
`keelline.toml`; at three the convention is code. Not in `keelline.areas`: that module is
imported by the hook registry, and `tests/test_areas.py` asserts that discovery in a clean
interpreter imports neither the configuration layer nor the presets — this module imports the
loader at module level and is imported only by `commands.py` modules.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from keelline.config.loader import load
from keelline.config.schema import Config


def common_flags(
    parser: argparse.ArgumentParser, *, store: bool = False
) -> argparse.ArgumentParser:
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    parser.add_argument("--machine", default=None, help="machine configuration file to read")
    if store:
        parser.add_argument("--store", default=None, help="resolve the memory store at this path")
    return parser


def root_and_config(args: argparse.Namespace) -> tuple[Path, Config]:
    root = Path(args.root).resolve()
    machine = Path(args.machine) if args.machine else None
    return root, load(root, machine=machine)
