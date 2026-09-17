"""The `setup` command surface: CLI wiring over `setup.run.setup` and `guards.githooks`.

`tests/setup/test_setup.py` and `tests/setup/test_git_hooks.py` already exercise the two
behaviours directly; what is untested until this file is the argparse wiring itself — the
group is registered, the flags reach the functions those tests call, and a real command-line
invocation exits 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run
from keelline.overlay.api import Completed


class _NullRunner:
    """Answers every call with success and runs nothing — the one runner this file's own
    CLI-level test may use, since installing the preset's plugins is otherwise unconditional
    and a test here must never reach a real `claude` or `codex`."""

    def run(self, argv: list[str], cwd: Path) -> Completed:
        return Completed(0, "", "")


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def test_the_command_is_discovered() -> None:
    help_text = build_parser(discover_registrars()).format_help()
    assert "setup" in help_text


def test_the_preset_flow_runs_through_the_cli_with_a_stubbed_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Patched at `overlay.api` itself, not at `setup.commands`: `run_setup` imports
    # `subprocess_runner` inside its own body (a deferred import, the same convention every
    # other `commands.py` in this tree uses), so the name it binds is whatever this module
    # attribute holds at call time.
    monkeypatch.setattr("keelline.overlay.api.subprocess_runner", lambda: _NullRunner())
    home = tmp_path / "home"
    machine = tmp_path / "config.toml"
    code = invoke(
        [
            "setup",
            "--preset",
            "recommended",
            "--yes",
            "--home",
            str(home),
            "--machine",
            str(machine),
        ]
    )
    assert code == 0
    assert (home / ".claude" / "settings.json").is_file()
    assert machine.is_file()


def test_git_hooks_and_preset_refuse_to_combine_through_the_cli(tmp_path: Path) -> None:
    code = invoke(["setup", "--preset", "recommended", "--git-hooks", "--root", str(tmp_path)])
    assert code == 2
