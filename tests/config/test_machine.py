from __future__ import annotations

from pathlib import Path

import pytest

from keelline.config.machine import machine_config_path, override_is_honoured


def test_the_override_is_ignored_when_the_caller_is_not_interactive(tmp_path: Path) -> None:
    env = {"KEELLINE_CONFIG": str(tmp_path / "hostile.toml"), "XDG_CONFIG_HOME": str(tmp_path)}
    assert machine_config_path(env, interactive=False) == tmp_path / "keelline" / "config.toml"


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


def test_xdg_config_home_still_selects_the_directory(tmp_path: Path) -> None:
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    assert machine_config_path(env) == tmp_path / "keelline" / "config.toml"
