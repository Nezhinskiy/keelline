from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from keelline.config.loader import CONFIG_FILE, load
from keelline.guards import bgcleanup
from keelline.guards.hooks import register
from keelline.hooks.api import EVENTS, Decision, Handler, HookEvent, Policy
from keelline.hooks.dispatch import Recorder, dispatch

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

LIST_IMPORTS = (
    "import sys\n"
    "from keelline.hooks.registry import discover\n"
    "names = [h.name for h in discover()]\n"
    "assert 'bg-cleanup' in names, names\n"
    "print(' '.join(sorted(m for m in sys.modules if m.startswith('keelline'))))\n"
)


def a_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / CONFIG_FILE).write_text(CONFIG, encoding="utf-8")
    return root


def bash_event(
    root: Path, command: str, *, background: bool = True, tool: str = "Bash"
) -> HookEvent:
    tool_input: dict[str, object] = {"command": command}
    if background:
        tool_input["run_in_background"] = True
    return HookEvent(
        name="PreToolUse",
        session_id="s1",
        agent_id=None,
        tool_name=tool,
        tool_input=tool_input,
        cwd=root,
        project_root=root,
        harness="claude",
        raw={"tool_name": tool, "tool_input": tool_input},
    )


def guard() -> Handler:
    return next(h for h in register() if h.name == "bg-cleanup")


def test_every_handler_declares_a_known_event() -> None:
    handlers = register()
    assert handlers != []
    for handler in handlers:
        assert handler.event in EVENTS


def test_the_background_guard_is_the_closed_pre_tool_use_handler() -> None:
    # D11: a guard for an action with a high cost of error fails closed. This is the only
    # CLOSED handler in the plugin, and the policy is the whole difference between "could not
    # judge" and "permitted".
    handler = guard()
    assert handler.event == "PreToolUse"
    assert handler.policy is Policy.CLOSED


def test_no_config_is_silence_for_every_handler(tmp_path: Path) -> None:
    # §12: "No keelline.toml → Plugin hooks silent." The guard included, by design.
    for handler in register():
        result = handler.run(bash_event(tmp_path, "sleep 300 &"), None)
        assert result.decision is None and result.context is None


def test_a_leaking_background_call_is_denied(tmp_path: Path) -> None:
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    result = guard().run(bash_event(root, "python -m http.server 8000 &"), config)
    assert result.decision is Decision.DENY
    assert result.reason == bgcleanup.LEAK_REASON


def test_a_non_bash_tool_is_ignored(tmp_path: Path) -> None:
    # Carries `run_in_background: true` deliberately: without it the flag check would be what
    # stops this event, and the assertion would say nothing about `tool_name`.
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    result = guard().run(bash_event(root, "sleep 300 &", tool="Edit"), config)
    assert result.decision is None


def test_a_trailing_restore_arrives_as_context_not_a_decision(tmp_path: Path) -> None:
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    command = "cp a a.bak; sed -i '' 's/x/y/' a; pytest; cp a.bak a"
    result = guard().run(bash_event(root, command, background=False), config)
    assert result.decision is None
    assert result.context is not None and "trap" in result.context


def test_a_guard_that_cannot_judge_refuses_rather_than_permits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The CLOSED policy, exercised through the real dispatcher: an exception inside the judge
    # is exit 2 with a reason, not an allow. Under Policy.OPEN this same call exits 0.
    def broken(command: str, *, background: bool) -> bgcleanup.Verdict:
        raise RuntimeError("boom")

    monkeypatch.setattr(bgcleanup, "judge", broken)
    root = a_project(tmp_path)
    config = load(root, machine=tmp_path / "absent.toml")
    recorder = Recorder()
    outcome = dispatch(bash_event(root, "ls"), register(), config, sink=recorder)
    assert outcome.exit_code == 2
    assert "bg-cleanup: RuntimeError: boom" in outcome.stderr
    assert recorder.records[0]["handler"] == "bg-cleanup"


def test_discovery_imports_no_guards_module_but_hooks(tmp_path: Path) -> None:
    # Every real import lives inside a handler body, so registering costs discovery nothing.
    completed = subprocess.run(
        [sys.executable, "-c", LIST_IMPORTS],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT / "src")},
    )
    assert completed.returncode == 0, completed.stderr
    imported = set(completed.stdout.split())
    assert "keelline.guards.hooks" in imported
    assert "keelline.guards.bgcleanup" not in imported
    assert "keelline.guards.bashscan" not in imported
    assert "keelline.config" not in imported


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
        },
    )


def test_a_leaking_background_call_is_denied_through_the_real_dispatcher(tmp_path: Path) -> None:
    # The production path end to end: stdin in, exit code out. This is what the wrapper runs.
    root = a_project(tmp_path)
    payload = {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "cwd": str(root),
        "tool_name": "Bash",
        "tool_input": {"command": "sleep 300 & wait", "run_in_background": True},
    }
    completed = hook("PreToolUse", json.dumps(payload), root)
    assert completed.returncode == 2
    assert "refused: bg-cleanup:" in completed.stderr
    allowed = dict(payload, tool_input={"command": "make && make test", "run_in_background": True})
    completed = hook("PreToolUse", json.dumps(allowed), root)
    assert completed.returncode == 0, completed.stderr
