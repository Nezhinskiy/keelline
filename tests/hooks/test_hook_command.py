# tests/hooks/test_hook_command.py
from __future__ import annotations

import argparse
import asyncio
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from keelline.guards.hygiene import LEAD
from keelline.hooks.api import Decision, Handler, HookEvent, HookResult, Policy
from keelline.hooks.commands import _output_cap, run_hook

ROOT = Path(__file__).resolve().parents[2]

CONFIG = """
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""


def hook(
    event: str, stdin: str, cwd: Path, *args: str, data: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Spawn `keelline hook <event> [args…]` with a fixed environment.

    `data` sets `CLAUDE_PLUGIN_DATA`, which is what makes the dispatcher's sink durable. The
    parameters are widened in place rather than a second spawner added beside this one, so
    every existing caller keeps its meaning.
    """
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(ROOT / "src"),
        "CLAUDE_PROJECT_DIR": str(cwd),
        "KEELLINE_CONFIG": str(cwd / "no-machine.toml"),
    }
    if data is not None:
        env["CLAUDE_PLUGIN_DATA"] = str(data)
    return subprocess.run(
        [sys.executable, "-m", "keelline", "hook", event, *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
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


def test_an_unknown_event_on_the_command_line_dispatches_to_nothing(tmp_path: Path) -> None:
    # The harness owns the event vocabulary on argv; only a *registered* handler's event is
    # validated, so a platform that adds an event must not make the wrapper refuse.
    completed = hook("SomethingNewEntirely", "{}", tmp_path)
    assert completed.returncode == 0
    output = json.loads(completed.stdout)["hookSpecificOutput"]
    assert output["hookEventName"] == "SomethingNewEntirely"
    assert "additionalContext" not in output


def test_a_repository_without_a_config_still_gets_the_shipped_cap() -> None:
    assert _output_cap(None) == 10000


@pytest.mark.parametrize(("event", "code"), [("PreToolUse", 2), ("SessionStart", 0)])
@pytest.mark.parametrize("raised", [asyncio.CancelledError(), KeyboardInterrupt()], ids=type)
def test_a_base_exception_inside_the_wrapper_keeps_the_event_aware_verdict(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raised: BaseException,
    event: str,
    code: int,
) -> None:
    # A Ctrl-C mid-hook raises KeyboardInterrupt, which does not inherit Exception: escaping
    # here would exit the process on the interpreter's own code, and PreToolUse reads anything
    # that is not 2 as permission.
    def interrupted() -> list[object]:
        raise raised

    monkeypatch.setattr("keelline.hooks.commands.discover", interrupted)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert run_hook(argparse.Namespace(event=event)) == code
    assert type(raised).__name__ in capsys.readouterr().err


@pytest.mark.parametrize("event", ["PreToolUse", "PostToolUse"])
def test_a_deny_with_a_malformed_context_still_refuses_through_the_wrapper(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], event: str
) -> None:
    # The production path, not `dispatch` alone: an OPEN handler that denies while carrying a
    # non-string context exited 0 and the tool call proceeded. PostToolUse is the discriminating
    # half — nothing there maps a stray internal error to 2, so only a genuinely recorded deny
    # can produce it.
    def deny(ev: HookEvent, config: object) -> HookResult:
        return HookResult(
            decision=Decision.DENY,
            reason="rm -rf / is refused",
            context=cast(str, {"n": 1}),
        )

    probe = Handler(name="probe", event=event, policy=Policy.OPEN, run=deny)
    monkeypatch.setattr("keelline.hooks.commands.discover", lambda: [probe])
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hook_event_name": event})))
    assert run_hook(argparse.Namespace(event=event)) == 2
    assert "refused: probe: rm -rf / is refused" in capsys.readouterr().err


def _initialised_project(tmp_path: Path) -> Path:
    """Every condition `test-hygiene` needs to fire, and nothing more.

    A `keelline.toml`, because both handlers are silent without a configuration; a git
    repository, because the notice's one reportable fault here is `hygiene.DIRTY`'s — and
    `keelline.toml` itself is the uncommitted change that produces it.
    """
    project = tmp_path / "project"
    project.mkdir()
    (project / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(project)], check=True, capture_output=True)
    return project


def _failing_test_run() -> str:
    """A PostToolUse payload `test-hygiene` answers: a red pytest run reported by exit code."""
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "a-session",
            "tool_name": "Bash",
            "tool_input": {"command": "uv run pytest -q"},
            "tool_response": {"exit_code": 1},
        }
    )


def test_a_once_per_context_handler_really_runs_once(tmp_path: Path) -> None:
    # Before the sink, `NullSink.seen()` was always False and `once_key` meant "every
    # invocation" — a once-per-context notice on every single tool call.
    #
    # The notice's own text is asserted, not the word "hygiene": `guards.hygiene` builds it from
    # `LEAD` and the two fault sentences, and none of them carries the handler's name. Asserting
    # only that both runs differ would pass with the sink deleted and the handler silent.
    data = tmp_path / "data"
    data.mkdir()
    project = _initialised_project(tmp_path)
    payload = _failing_test_run()
    first = hook("PostToolUse", payload, project, data=data)
    second = hook("PostToolUse", payload, project, data=data)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"].startswith(LEAD)
    assert json.loads(second.stdout)["hookSpecificOutput"].get("additionalContext") is None
