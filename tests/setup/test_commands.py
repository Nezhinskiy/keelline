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
from keelline.runner import Completed


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


def test_the_machine_default_is_the_file_every_reader_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review finding 14. `--machine`'s default was `machine_config_path()` with no argument —
    # the only such call in the tree — so it took the `isatty` sniff that every *reader* pins
    # with `interactive=False`. With `XDG_CONFIG_HOME` set, an owner running `keelline setup`
    # in their own shell wrote `/xdg/keelline/config.toml`, got exit 0, and every reader then
    # said "no overlay root is recorded in the machine configuration; run `keelline setup`" —
    # the defect `config.loader.load`'s docstring says it fixed, reintroduced on the write side.
    #
    # Mutation (`mutations.toml`, "setup's --machine default takes the interactive sniff"):
    # `interactive=False` is dropped from the call in `run_setup` → the file lands under
    # `XDG_CONFIG_HOME` and this reddens on both paths below.
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    # An interactive shell is what makes the sniff answer yes; the reader's answer must not
    # depend on it.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    stub = _NullRunner()
    monkeypatch.setattr("keelline.setup.commands.subprocess_runner", lambda: stub)
    assert invoke(["setup", "--preset", "recommended", "--yes", "--home", str(home)]) == 0
    assert (home / ".config" / "keelline" / "config.toml").is_file()
    assert not (xdg / "keelline" / "config.toml").exists()
    assert stub.calls, "the stubbed runner was never called; the patch may have stopped applying"


def test_setup_help_names_no_path_from_the_machine_the_parser_was_built_on(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The second half of the same finding: both defaults used to be computed when the parser is
    # built, so `keelline setup --help` printed the developer's own home directory — and it was
    # computed on every run of every command, since the parser is built for all of them.
    with pytest.raises(SystemExit):
        invoke(["setup", "--help"])
    printed = capsys.readouterr().out
    assert "--machine" in printed
    assert str(Path.home()) not in printed
    assert "~/.config/keelline/config.toml" in printed
