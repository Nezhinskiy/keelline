from __future__ import annotations

from pathlib import Path

import pytest

from keelline.config.machine import machine_config_path, override_is_honoured


def test_the_override_is_ignored_when_the_caller_is_not_interactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Both variables reach the same file, so the assertion is the *fallback* path and not the
    # one either variable chose. Asserting `tmp_path / "keelline" / "config.toml"` here — the
    # location `XDG_CONFIG_HOME` picks — is what let the gate on `KEELLINE_CONFIG` pass while
    # its ungated sibling three lines below honoured the repository's choice anyway.
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    env = {
        "KEELLINE_CONFIG": str(tmp_path / "hostile.toml"),
        "XDG_CONFIG_HOME": str(tmp_path / "hostile-dir"),
    }
    assert machine_config_path(env, interactive=False) == (
        home / ".config" / "keelline" / "config.toml"
    )


def test_xdg_config_home_is_ignored_when_the_caller_is_not_interactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The variable on its own, with no `KEELLINE_CONFIG` beside it: a repository that sets only
    # this one costs itself a path segment and nothing else, so it must be refused alone too.
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert machine_config_path({"XDG_CONFIG_HOME": str(tmp_path)}, interactive=False) == (
        home / ".config" / "keelline" / "config.toml"
    )


def test_the_override_is_honoured_from_an_interactive_shell(tmp_path: Path) -> None:
    env = {"KEELLINE_CONFIG": str(tmp_path / "mine.toml"), "XDG_CONFIG_HOME": str(tmp_path)}
    assert machine_config_path(env, interactive=True) == tmp_path / "mine.toml"


def test_the_default_is_not_interactive_under_a_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    class NotATty:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("sys.stdin", NotATty())
    assert override_is_honoured() is False


def test_a_stdin_that_cannot_answer_is_not_interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", None)
    assert override_is_honoured() is False


def test_xdg_config_home_selects_the_directory_from_an_interactive_shell(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    assert machine_config_path(env, interactive=True) == tmp_path / "keelline" / "config.toml"
