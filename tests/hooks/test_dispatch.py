# tests/hooks/test_dispatch.py
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from keelline.hooks.api import Decision, Handler, HookEvent, HookResult, Policy
from keelline.hooks.dispatch import TRUNCATION_MARK, Recorder, dispatch, parse_event

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


def handler(
    name: str,
    policy: Policy,
    result: HookResult | BaseException,
    once_key: str | None = None,
) -> Handler:
    def run(ev: HookEvent, config: object) -> HookResult:
        if isinstance(result, BaseException):
            raise result
        return result

    return Handler(name=name, event="PreToolUse", policy=policy, run=run, once_key=once_key)


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
    handlers = [handler("g", Policy.CLOSED, HookResult(decision=Decision.DENY, reason="no"))]
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


def test_a_policy_that_arrived_as_a_plain_string_still_closes() -> None:
    # A lane that builds a Handler dynamically hands us "closed", not Policy.CLOSED; mypy
    # cannot see that, so the cast stands in for it.
    closed = cast(Policy, "closed")
    outcome = dispatch(event(), [handler("g", closed, RuntimeError("boom"))], None)
    assert outcome.exit_code == 2


def test_a_closed_handler_that_calls_sys_exit_refuses() -> None:
    outcome = dispatch(event(), [handler("g", Policy.CLOSED, SystemExit(0))], None)
    assert outcome.exit_code == 2
    assert "SystemExit" in outcome.stderr


def test_an_unrecognised_decision_does_not_refuse_but_is_recorded() -> None:
    recorder = Recorder()
    result = HookResult(decision=cast(Decision, "block"))
    outcome = dispatch(event(), [handler("a", Policy.OPEN, result)], None, sink=recorder)
    assert outcome.exit_code == 0
    assert recorder.records[0]["error"] == "unrecognised-decision"
    assert recorder.records[0]["decision"] == "block"


def test_policy_is_taken_from_handlers_that_failed_not_from_all_registered() -> None:
    handlers = [
        handler("g", Policy.CLOSED, HookResult()),
        handler("a", Policy.OPEN, RuntimeError("boom")),
    ]
    assert dispatch(event(), handlers, None).exit_code == 0


def test_a_cap_below_the_envelope_is_recorded_and_emits_nothing() -> None:
    # No JSON envelope fits in 20 characters, so the honest output is none at all: anything
    # longer than the cap is replaced by the platform with a preview and a file path (§9.5).
    recorder = Recorder()
    handlers = [handler("a", Policy.OPEN, HookResult(context="x" * 50))]
    outcome = dispatch(event(), handlers, None, sink=recorder, cap=20)
    assert len(outcome.stdout) <= 20
    assert recorder.records[0]["error"] == "context-truncated"


def test_context_at_a_realistic_cap_keeps_its_leading_content_and_the_mark() -> None:
    handlers = [handler("a", Policy.OPEN, HookResult(context="y" * 500))]
    outcome = dispatch(event(), handlers, None, cap=200)
    context = json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"]
    assert len(outcome.stdout) <= 200
    assert len(outcome.stdout) > 200 - len(TRUNCATION_MARK)  # the budget is spent, not abandoned
    assert context.startswith("y" * 8)
    assert context.endswith(TRUNCATION_MARK)


def test_the_cap_bounds_the_emitted_string_not_the_field_inside_it() -> None:
    handlers = [handler("a", Policy.OPEN, HookResult(context="x" * 20000))]
    outcome = dispatch(event(), handlers, None, cap=10000)
    assert len(outcome.stdout) <= 10000
    context = json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context.endswith(TRUNCATION_MARK)


def test_json_escaping_is_charged_to_the_same_budget() -> None:
    handlers = [handler("a", Policy.OPEN, HookResult(context="\n" * 500))]
    outcome = dispatch(event(), handlers, None, cap=200)
    assert len(outcome.stdout) <= 200
    context = json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context.endswith(TRUNCATION_MARK)


def test_a_once_per_context_handler_runs_once_and_is_skipped_afterwards() -> None:
    recorder = Recorder()
    once = handler("a", Policy.OPEN, HookResult(context="A"), once_key="ledger-notes")
    first = json.loads(dispatch(event(), [once], None, sink=recorder).stdout)
    second = json.loads(dispatch(event(), [once], None, sink=recorder).stdout)
    assert first["hookSpecificOutput"]["additionalContext"] == "A"
    assert "additionalContext" not in second["hookSpecificOutput"]
    assert recorder.marks == {"ledger-notes"}


def test_a_handler_without_a_once_key_runs_every_time() -> None:
    recorder = Recorder()
    every = handler("a", Policy.OPEN, HookResult(context="A"))
    for _ in range(2):
        outcome = dispatch(event(), [every], None, sink=recorder)
        assert json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"] == "A"
    assert recorder.marks == set()


def test_a_once_per_context_handler_that_raises_is_not_marked() -> None:
    recorder = Recorder()
    once = handler("a", Policy.OPEN, RuntimeError("boom"), once_key="ledger-notes")
    assert "boom" in dispatch(event(), [once], None, sink=recorder).stderr
    assert recorder.marks == set()
    assert "boom" in dispatch(event(), [once], None, sink=recorder).stderr


def test_one_handler_cannot_blank_what_the_next_one_reads() -> None:
    seen: list[object] = []

    def blank(ev: HookEvent, config: object) -> HookResult:
        ev.tool_input["command"] = ""
        ev.raw["tool_name"] = "Write"
        return HookResult()

    def read(ev: HookEvent, config: object) -> HookResult:
        seen.append(ev.tool_input.get("command"))
        seen.append(ev.raw.get("tool_name"))
        return HookResult()

    handlers = [
        Handler(name="a-blank", event="PreToolUse", policy=Policy.OPEN, run=blank),
        Handler(name="b-read", event="PreToolUse", policy=Policy.OPEN, run=read),
    ]
    dispatch(event(tool_input={"command": "rm -rf /"}), handlers, None)
    assert seen == ["rm -rf /", "Bash"]


def test_non_string_contract_fields_become_none_instead_of_reaching_a_guard() -> None:
    ev = parse_event(
        {
            "hook_event_name": "PreToolUse",
            "cwd": "/tmp",
            "session_id": 7,
            "agent_id": ["a"],
            "tool_name": {"name": "Bash"},
        },
        env=CLAUDE_ENV,
    )
    assert ev.session_id is None
    assert ev.agent_id is None
    assert ev.tool_name is None


def test_project_root_prefers_the_claude_variable_over_git(tmp_path: Path) -> None:
    ev = parse_event({"hook_event_name": "SessionStart", "cwd": str(tmp_path)}, env=CLAUDE_ENV)
    assert ev.project_root == Path("/p")
    assert ev.harness == "claude"


def _forbidden(cwd: Path) -> Path | None:
    raise AssertionError(f"git was forked for {cwd}")


def test_the_walk_finds_the_root_through_a_git_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "a" / "b").mkdir(parents=True)
    monkeypatch.setattr("keelline.hooks.dispatch._git_toplevel", _forbidden)
    ev = parse_event({"hook_event_name": "PreToolUse", "cwd": str(tmp_path / "a" / "b")}, env={})
    assert ev.project_root == tmp_path


def test_the_walk_finds_the_root_through_a_git_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A worktree and a submodule carry `.git` as a file, so `is_dir()` would miss both.
    (tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/w\n", encoding="utf-8")
    (tmp_path / "a").mkdir()
    monkeypatch.setattr("keelline.hooks.dispatch._git_toplevel", _forbidden)
    ev = parse_event({"hook_event_name": "PreToolUse", "cwd": str(tmp_path / "a")}, env={})
    assert ev.project_root == tmp_path


def test_git_is_still_asked_when_the_walk_finds_no_dot_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[Path] = []

    def fake(cwd: Path) -> Path | None:
        asked.append(cwd)
        return Path("/from-git")

    monkeypatch.setattr("keelline.hooks.dispatch._git_toplevel", fake)
    ev = parse_event({"hook_event_name": "PreToolUse", "cwd": str(tmp_path)}, env={})
    assert ev.project_root == Path("/from-git")
    assert asked == [tmp_path]


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
