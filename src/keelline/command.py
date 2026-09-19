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

# One sentence per shared flag (DC4). `--root` and `--machine` were spelled by hand in three
# parsers besides this one and had already drifted from these words; `--home` appeared in two
# areas with two sentences, one saying "read" and the other "write". A flag that means the same
# thing across eight commands says the same thing, and `tests/test_command.py` walks the real
# parser and holds every occurrence to the constant.
ROOT_HELP = "project root (default: current directory)"
MACHINE_HELP = "machine configuration file to read"
STORE_HELP = "resolve the memory store at this path"
DRY_RUN_HELP = "report what would change and write nothing"
HOME_HELP = "the home directory to read and write under (default: the real one)"
# The named exceptions: each is one sentence, spelled here and used by exactly one parser,
# and `tests/test_command.py` holds the parser to it by name. An entry is a decision that the
# flag means something other than the shared thing, not a convenience for a sentence someone
# liked better.
OVERLAY_ROOT_HELP = "the overlay root (default: current directory)"
INSTANCE_DIR_HELP = "directory to create it in (default: current directory)"
SETUP_ROOT_HELP = (
    "the repository --git-hooks installs into, and the project root --overlay must not be "
    "recorded inside of (default: .)"
)
SETUP_MACHINE_HELP = (
    "the machine configuration file to write (default: ~/.config/keelline/config.toml, the "
    "file every reader reads)"
)


def common_flags(
    parser: argparse.ArgumentParser, *, store: bool = False
) -> argparse.ArgumentParser:
    parser.add_argument("--root", default=".", help=ROOT_HELP)
    parser.add_argument("--machine", default=None, help=MACHINE_HELP)
    if store:
        parser.add_argument("--store", default=None, help=STORE_HELP)
    return parser


def root_and_config(args: argparse.Namespace) -> tuple[Path, Config]:
    root = Path(args.root).resolve()
    machine = Path(args.machine) if args.machine else None
    return root, load(root, machine=machine)
