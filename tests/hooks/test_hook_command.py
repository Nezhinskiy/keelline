# tests/hooks/test_hook_command.py
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from keelline.hooks.commands import _output_cap

ROOT = Path(__file__).resolve().parents[2]


def hook(event: str, stdin: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "keelline", "hook", event],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env={
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(ROOT / "src"),
            "CLAUDE_PROJECT_DIR": str(cwd),
            "KEELLINE_CONFIG": str(cwd / "no-machine.toml"),
        },
    )


def test_no_handlers_means_a_clean_empty_outcome(tmp_path: Path) -> None:
    completed = hook("SessionStart", json.dumps({"hook_event_name": "SessionStart"}), tmp_path)
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_malformed_stdin_on_pre_tool_use_refuses(tmp_path: Path) -> None:
    completed = hook("PreToolUse", "{not json", tmp_path)
    assert completed.returncode == 2
    assert "refused" in completed.stderr


def test_malformed_stdin_on_session_start_degrades_open(tmp_path: Path) -> None:
    completed = hook("SessionStart", "{not json", tmp_path)
    assert completed.returncode == 0
    assert "keelline" in completed.stderr


def test_a_broken_repository_config_on_pre_tool_use_refuses(tmp_path: Path) -> None:
    # Valid everywhere the loader checks before [ci], so the not-a-table shape is the defect
    # this reaches (a top-level key must precede every table header in TOML).
    (tmp_path / "keelline.toml").write_text(
        'ci = "not-a-table"\n\n[keelline]\nversion = "0.1.0"\n\n[project]\nname = "demo"\n',
        encoding="utf-8",
    )
    completed = hook("PreToolUse", json.dumps({"hook_event_name": "PreToolUse"}), tmp_path)
    assert completed.returncode == 2


def test_argv_names_the_event_even_when_stdin_spells_it_differently(tmp_path: Path) -> None:
    completed = hook("PreToolUse", json.dumps({"hook_event_name": "pre_tool_use"}), tmp_path)
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_a_repository_without_a_config_still_gets_the_shipped_cap() -> None:
    assert _output_cap(None) == 10000
