# tests/hooks/test_dispatch.py
from __future__ import annotations

import json
from pathlib import Path

from keelline.hooks.api import Handler, HookEvent, HookResult, Policy
from keelline.hooks.dispatch import Recorder, dispatch, parse_event

CLAUDE_ENV = {"CLAUDE_PROJECT_DIR": "/p", "CLAUDE_PLUGIN_ROOT": "/r"}


def event(name: str = "PreToolUse", **raw: object) -> HookEvent:
    payload: dict[str, object] = {
        "hook_event_name": name,
        "session_id": "s",
        "cwd": "/tmp",
        "tool_name": "Bash",
    }
    payload.update(raw)
    return parse_event(payload, env=CLAUDE_ENV)


def handler(name: str, policy: Policy, result: HookResult | Exception) -> Handler:
    def run(ev: HookEvent, config: object) -> HookResult:
        if isinstance(result, Exception):
            raise result
        return result

    return Handler(name=name, event="PreToolUse", policy=policy, run=run)


def test_contexts_are_joined_into_the_claude_shape() -> None:
    handlers = [
        handler("a", Policy.OPEN, HookResult(context="A")),
        handler("b", Policy.OPEN, HookResult(context="B")),
    ]
    outcome = dispatch(event(), handlers, config=None)
    assert outcome.exit_code == 0
    assert json.loads(outcome.stdout) == {
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "A\n\nB"}
    }


def test_a_deny_from_a_handler_exits_two_with_its_reason() -> None:
    handlers = [handler("g", Policy.CLOSED, HookResult(decision="deny", reason="no"))]
    outcome = dispatch(event(), handlers, config=None)
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"
    assert "no" in outcome.stderr


def test_an_open_handler_that_raises_is_swallowed_and_recorded() -> None:
    recorder = Recorder()
    outcome = dispatch(
        event(), [handler("a", Policy.OPEN, RuntimeError("boom"))], None, sink=recorder
    )
    assert outcome.exit_code == 0
    assert "boom" in outcome.stderr
    assert recorder.records[0]["handler"] == "a"
    assert recorder.records[0]["error"] == "RuntimeError"


def test_a_closed_handler_that_raises_refuses() -> None:
    outcome = dispatch(event(), [handler("g", Policy.CLOSED, RuntimeError("boom"))], None)
    assert outcome.exit_code == 2
    assert "boom" in outcome.stderr


def test_policy_is_taken_from_handlers_that_failed_not_from_all_registered() -> None:
    handlers = [
        handler("g", Policy.CLOSED, HookResult()),
        handler("a", Policy.OPEN, RuntimeError("boom")),
    ]
    assert dispatch(event(), handlers, None).exit_code == 0


def test_context_above_the_cap_is_truncated_and_recorded() -> None:
    recorder = Recorder()
    handlers = [handler("a", Policy.OPEN, HookResult(context="x" * 50))]
    outcome = dispatch(event(), handlers, None, sink=recorder, cap=20)
    context = json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"]
    assert len(context) <= 20
    assert recorder.records[0]["error"] == "context-truncated"


def test_project_root_prefers_the_claude_variable_over_git(tmp_path: Path) -> None:
    ev = parse_event({"hook_event_name": "SessionStart", "cwd": str(tmp_path)}, env=CLAUDE_ENV)
    assert ev.project_root == Path("/p")
    assert ev.harness == "claude"


def test_codex_is_detected_by_its_own_variable_even_beside_the_claude_ones() -> None:
    env = {"PLUGIN_ROOT": "/x", "CLAUDE_PLUGIN_ROOT": "/x"}
    ev = parse_event({"hook_event_name": "SessionStart", "cwd": "/tmp"}, env=env)
    assert ev.harness == "codex"


def test_codex_is_detected_by_the_stdin_fields_s1_recorded() -> None:
    payload = {
        "hook_event_name": "SessionStart",
        "cwd": "/tmp",
        "model": "m",
        "permission_mode": "p",
    }
    ev = parse_event(payload, env={"CLAUDE_PLUGIN_ROOT": "/x"})
    assert ev.harness == "codex"
