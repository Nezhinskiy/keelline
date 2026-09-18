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
    and a test here must never reach a real `claude` or `codex`.

    `calls` is asserted non-empty by its one caller below (Fix round 1, item 5): the only thing
    standing between this test and four real plugin/marketplace calls against the developer's
    own machine is the monkeypatch two lines down, and an empty `calls` list is exactly what a
    silently-broken patch would look like — the real `subprocess_runner()` would have run
    instead of this one, and nothing here would notice without this assertion.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        return Completed(0, "", "")


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def test_the_command_is_discovered() -> None:
    help_text = build_parser(discover_registrars()).format_help()
    assert "setup" in help_text


def test_the_preset_flow_runs_through_the_cli_with_a_stubbed_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Patched at `keelline.setup.commands` itself, not at `overlay.api`: that module-level
    # import (Fix round 1, item 5) is what `run_setup` now calls directly, so a test that wants
    # to keep this command away from a real `claude`/`codex` monkeypatches a name this module
    # owns rather than reaching two hops into a dependency's own attribute.
    stub = _NullRunner()
    monkeypatch.setattr("keelline.setup.commands.subprocess_runner", lambda: stub)
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
    # The seam actually fired: at least the marketplace-add call reached the stub rather than
    # a real binary. An empty list here would mean the patch above stopped applying.
    assert stub.calls, "the stubbed runner was never called; the patch may have stopped applying"


def test_git_hooks_and_preset_refuse_to_combine_through_the_cli(tmp_path: Path) -> None:
    code = invoke(["setup", "--preset", "recommended", "--git-hooks", "--root", str(tmp_path)])
    assert code == 2
