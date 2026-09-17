"""The `setup` command (§5.2): configure this machine from a preset, once.

One command and not a group with subcommands, the same shape `attach`/`detach` take: `setup`
does one of two things depending on which flags are given (Task 14 adds the second, the
per-repository git hook), and neither is a subcommand of the other because a subcommand would
still need `--root` to make sense of `--git-hooks` while the machine-level flags stay siblings
of it rather than children.

`--home` and `--machine` are not test affordances bolted on afterwards: the Global Constraints
forbid a test from touching the developer's real `~/.claude` or `~/.config/keelline/`, and a
command whose only mode writes to the real ones could not be tested at all. Both default to the
real paths, exactly as `--root` defaults to the current directory elsewhere in this CLI.

`--machine` is **not** gated behind an interactive shell here, unlike `attach`/`detach`'s. That
gate is about a flag that decides which overlay a *read* trusts (DP3); `setup` is the command
that *writes* the machine file in the first place, so gating its own `--machine` would refuse
the very thing this command exists to do, on every non-interactive run — including the CLI
exit check this plan's own brief runs. Scoped to `attach`/`detach` on purpose, and left there.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from keelline.areas import SubParsers
from keelline.result import Result


def run_setup(args: argparse.Namespace) -> Result:
    from keelline.overlay.api import subprocess_runner
    from keelline.setup.run import setup

    home = Path(args.home).expanduser()
    machine = Path(args.machine).expanduser()
    report = setup(
        args.preset or "recommended",
        home=home,
        machine=machine,
        runner=subprocess_runner(),
        yes=args.yes,
        overlay=args.overlay,
    )
    data = {
        "machine_written": report.machine_written,
        "plugins_installed": list(report.plugins_installed),
        "deny_written": report.deny_written,
        "cli_on_path": report.cli_on_path,
        "overlay": str(report.overlay) if report.overlay is not None else None,
        "notes": list(report.notes),
    }
    summary = "; ".join(
        (
            f"machine configuration written to {machine}",
            f"{len(report.plugins_installed)} plugin(s) installed",
            "deny rules merged" if report.deny_written else "deny rules unchanged",
            "keelline is on PATH" if report.cli_on_path else "keelline is not on PATH",
            f"overlay recorded at {report.overlay}" if report.overlay else "no overlay recorded",
            *report.notes,
        )
    )
    return Result(summary, data)


def register(groups: SubParsers) -> None:
    from keelline.config.machine import machine_config_path
    from keelline.setup.machine import USER_SETTINGS

    setup = groups.add_parser("setup", help="configure this machine from a preset")
    setup.add_argument(
        "--preset", default=None, help="the preset to install (default: recommended)"
    )
    setup.add_argument(
        "--yes",
        action="store_true",
        help="take the detected defaults for everything except the overlay",
    )
    setup.add_argument(
        "--home",
        default=str(Path.home()),
        help=f"where to write {USER_SETTINGS} (default: the real home directory)",
    )
    setup.add_argument(
        "--machine",
        default=str(machine_config_path()),
        help="the machine configuration file to write (default: the usual one)",
    )
    setup.add_argument(
        "--overlay",
        default=None,
        help=(
            "record an existing overlay by path, or create one with "
            "create:<owner>/<name> (asks GitHub for a private repository from the template)"
        ),
    )
    setup.set_defaults(func=run_setup)
