# tests/hooks/test_dispatch.py
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

import pytest

from keelline.hooks.api import Decision, Handler, HookEvent, HookResult, NullSink, Policy
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
    event_name: str = "PreToolUse",
) -> Handler:
    def run(ev: HookEvent, config: object) -> HookResult:
        if isinstance(result, BaseException):
            raise result
        return result

    return Handler(name=name, event=event_name, policy=policy, run=run, once_key=once_key)


def test_contexts_are_joined_into_the_claude_shape() -> None:
    handlers = [
        handler("a", Policy.OPEN, HookResult(context="A")),
        handler("b", Policy.OPEN, HookResult(context="B")),
    ]
    outcome = dispatch(event(), handlers, config=None, sink=Recorder())
    assert outcome.exit_code == 0
    assert json.loads(outcome.stdout) == {
        "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "A\n\nB"}
    }


@pytest.mark.parametrize(
    ("registered", "other"), [("PostToolUse", "PreToolUse"), ("PreToolUse", "PostToolUse")]
)
def test_a_handler_stays_silent_on_every_event_but_its_own(registered: str, other: str) -> None:
    # `discover()` hands the dispatcher every area's handlers at once, so the event filter is
    # the only thing keeping a PostToolUse guard from refusing a PreToolUse call.
    guard = handler(
        "g", Policy.CLOSED, HookResult(decision=Decision.DENY, reason="no"), event_name=registered
    )
    assert dispatch(event(registered), [guard], None, sink=Recorder()).exit_code == 2
    silent = dispatch(event(other), [guard], None, sink=Recorder())
    assert silent.exit_code == 0
    assert silent.stderr == ""


def test_a_decision_that_arrived_as_a_plain_string_still_denies() -> None:
    # A lane building a HookResult dynamically hands us "deny", not Decision.DENY. `Decision` is
    # a StrEnum, so the comparison must be by value: under identity this deny would be an
    # unrecognised verdict instead, which an OPEN handler's policy swallows.
    result = HookResult(decision=cast(Decision, "deny"))
    outcome = dispatch(event(), [handler("a", Policy.OPEN, result)], None, sink=Recorder())
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"


def test_a_deny_from_a_handler_exits_two_with_its_reason() -> None:
    handlers = [handler("g", Policy.CLOSED, HookResult(decision=Decision.DENY, reason="no"))]
    outcome = dispatch(event(), handlers, config=None, sink=Recorder())
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
    outcome = dispatch(
        event(), [handler("g", Policy.CLOSED, RuntimeError("boom"))], None, sink=Recorder()
    )
    assert outcome.exit_code == 2
    assert "boom" in outcome.stderr


def test_a_policy_that_arrived_as_a_plain_string_still_closes() -> None:
    # A lane that builds a Handler dynamically hands us "closed", not Policy.CLOSED; mypy
    # cannot see that, so the cast stands in for it.
    closed = cast(Policy, "closed")
    outcome = dispatch(event(), [handler("g", closed, RuntimeError("boom"))], None, sink=Recorder())
    assert outcome.exit_code == 2


def test_a_closed_handler_that_calls_sys_exit_refuses() -> None:
    outcome = dispatch(event(), [handler("g", Policy.CLOSED, SystemExit(0))], None, sink=Recorder())
    assert outcome.exit_code == 2
    assert "SystemExit" in outcome.stderr


def test_an_unrecognised_decision_under_an_open_policy_is_swallowed_with_a_reason() -> None:
    recorder = Recorder()
    result = HookResult(decision=cast(Decision, "block"))
    outcome = dispatch(event(), [handler("a", Policy.OPEN, result)], None, sink=recorder)
    assert outcome.exit_code == 0
    # Production reads stderr and never reads the sink, so the reason must be on both.
    assert "unrecognised decision 'block'" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-decision"
    assert recorder.records[0]["decision"] == "block"


@pytest.mark.parametrize("decision", ["DENY", "block", True, 7, None.__class__])
def test_an_unrecognised_decision_under_a_closed_policy_refuses(decision: object) -> None:
    # A guard that means to deny but misnames its verdict must not read as permission: the
    # malformed verdict is that handler failing, and a CLOSED handler's failure refuses.
    recorder = Recorder()
    result = HookResult(decision=cast(Decision, decision))
    outcome = dispatch(event(), [handler("g", Policy.CLOSED, result)], None, sink=recorder)
    assert outcome.exit_code == 2
    assert "unrecognised decision" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-decision"


def test_an_open_handlers_non_string_context_is_swallowed_and_a_later_one_lands() -> None:
    # `result.context` used to be joined into the payload outside every per-handler `try`, so
    # one OPEN handler's malformed context took the whole dispatch down with a TypeError instead
    # of being judged by that handler's own policy the way a malformed decision already is.
    recorder = Recorder()
    broken = handler("a-broken", Policy.OPEN, HookResult(context=cast(str, 42)))
    ok = handler("b-ok", Policy.OPEN, HookResult(context="B"))
    outcome = dispatch(event(), [broken, ok], None, sink=recorder)
    assert outcome.exit_code == 0
    assert "unrecognised context" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-context"
    assert recorder.records[0]["context"] == "42"
    assert json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"] == "B"


def test_a_closed_handlers_non_string_context_refuses() -> None:
    recorder = Recorder()
    result = HookResult(context=cast(str, 42))
    outcome = dispatch(event(), [handler("g", Policy.CLOSED, result)], None, sink=recorder)
    assert outcome.exit_code == 2
    assert "unrecognised context" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-context"


@pytest.mark.parametrize("policy", [Policy.OPEN, Policy.CLOSED])
@pytest.mark.parametrize("decision", [Decision.DENY, "deny"], ids=["enum", "string"])
def test_a_deny_carrying_a_malformed_context_still_refuses_and_records_the_failure(
    policy: Policy, decision: object
) -> None:
    # One result carries both the deny and the malformed context, so the order the two are read
    # in decides the exit code. Validating `context` above the decision branch failed the handler
    # before its deny was ever recorded, and an OPEN handler's policy then swallowed the whole
    # result — a live deny converted into an allow by an ordinary neighbouring bug. The decision
    # is read first now, and the context failure is still judged, on top of the refusal.
    recorder = Recorder()
    result = HookResult(
        decision=cast(Decision, decision),
        reason="rm -rf / is refused",
        context=cast(str, {"n": 1}),
    )
    outcome = dispatch(event(), [handler("g", policy, result)], None, sink=recorder)
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"
    assert "g: rm -rf / is refused" in outcome.stderr
    # Production reads stderr and never reads the sink, so the failure must reach both.
    assert "unrecognised context {'n': 1}" in outcome.stderr
    assert recorder.records[0]["error"] == "unrecognised-context"
    assert recorder.records[0]["context"] == "{'n': 1}"


def test_an_earlier_deny_survives_a_later_handlers_malformed_context() -> None:
    # Not PreToolUse: there `run_hook`'s blanket catch maps any internal error to 2 anyway, so
    # the lost deny is invisible. Everywhere else an escaped TypeError left the process at 0.
    recorder = Recorder()
    deny = handler(
        "a-deny",
        Policy.CLOSED,
        HookResult(decision=Decision.DENY, reason="no"),
        event_name="PostToolUse",
    )
    broken = handler(
        "b-broken", Policy.OPEN, HookResult(context=cast(str, 42)), event_name="PostToolUse"
    )
    outcome = dispatch(event("PostToolUse"), [deny, broken], None, sink=recorder)
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"
    assert "a-deny: no" in outcome.stderr


@pytest.mark.parametrize("policy", [Policy.CLOSED, Policy.OPEN])
@pytest.mark.parametrize("raised", [asyncio.CancelledError(), KeyboardInterrupt()], ids=type)
def test_a_base_exception_from_a_handler_is_judged_by_that_handlers_policy(
    policy: Policy, raised: BaseException
) -> None:
    # A handler that awaits anything surfaces CancelledError and a Ctrl-C mid-hook surfaces
    # KeyboardInterrupt; neither inherits Exception, so both used to escape every guard and
    # exit the process on something that is not 2 — a CLOSED guard reading as an allow.
    # CancelledError leads: a regression on it fails one test, where KeyboardInterrupt aborts
    # the whole session and would otherwise be the only signal.
    recorder = Recorder()
    outcome = dispatch(event(), [handler("g", policy, raised)], None, sink=recorder)
    assert outcome.exit_code == (2 if policy == Policy.CLOSED else 0)
    assert type(raised).__name__ in outcome.stderr
    assert recorder.records[0]["error"] == type(raised).__name__


def test_an_earlier_deny_survives_a_later_handlers_malformed_return() -> None:
    # Not PreToolUse: there `run_hook`'s blanket catch maps any internal error to 2 anyway, so
    # the lost deny is invisible. Everywhere else the AttributeError left the process at 0.
    recorder = Recorder()
    deny = handler(
        "a-deny",
        Policy.CLOSED,
        HookResult(decision=Decision.DENY, reason="no"),
        event_name="PostToolUse",
    )
    broken = handler("b-broken", Policy.OPEN, cast(HookResult, None), event_name="PostToolUse")
    outcome = dispatch(event("PostToolUse"), [deny, broken], None, sink=recorder)
    assert outcome.exit_code == 2
    assert outcome.decision == "deny"
    assert "a-deny: no" in outcome.stderr
    assert recorder.records[0] == {
        "event": "PostToolUse",
        "handler": "b-broken",
        "error": "TypeError",
    }


def test_a_null_sink_forgets_a_marker_instead_of_suppressing_it() -> None:
    # The shipped `run_hook` passes a NullSink, so this is production's `once_key` semantics.
    sink = NullSink()
    sink.mark("ledger-notes")
    assert sink.seen("ledger-notes") is False


def test_a_once_key_handler_runs_every_time_under_the_null_sink() -> None:
    runs: list[int] = []

    def count(ev: HookEvent, config: object) -> HookResult:
        runs.append(1)
        return HookResult(context="A")

    once = Handler(
        name="a", event="PreToolUse", policy=Policy.OPEN, run=count, once_key="ledger-notes"
    )
    for _ in range(2):
        dispatch(event(), [once], None, sink=NullSink())
    assert runs == [1, 1]


def test_policy_is_taken_from_handlers_that_failed_not_from_all_registered() -> None:
    handlers = [
        handler("g", Policy.CLOSED, HookResult()),
        handler("a", Policy.OPEN, RuntimeError("boom")),
    ]
    assert dispatch(event(), handlers, None, sink=Recorder()).exit_code == 0


def test_a_cap_below_the_envelope_is_recorded_and_emits_nothing() -> None:
    # No JSON envelope fits in 20 characters, so the honest output is none at all: anything
    # longer than the cap is replaced by the platform with a preview and a file path (§9.5).
    recorder = Recorder()
    handlers = [handler("a", Policy.OPEN, HookResult(context="x" * 50))]
    outcome = dispatch(event(), handlers, None, sink=recorder, cap=20)
    assert outcome.stdout == ""
    assert recorder.records[0]["error"] == "context-truncated"


def test_context_at_a_realistic_cap_keeps_its_leading_content_and_the_mark() -> None:
    handlers = [handler("a", Policy.OPEN, HookResult(context="y" * 500))]
    outcome = dispatch(event(), handlers, None, sink=Recorder(), cap=200)
    context = json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"]
    # Every kept character here is plain ASCII, so nothing widens under JSON escaping and the
    # search always lands exactly on the cap: 69 kept characters plus the mark is the true
    # optimum for this event name and context, not merely a value close enough to it.
    assert len(outcome.stdout) == 200
    assert context == "y" * 69 + TRUNCATION_MARK


def test_the_cap_bounds_the_emitted_string_not_the_field_inside_it() -> None:
    handlers = [handler("a", Policy.OPEN, HookResult(context="x" * 20000))]
    outcome = dispatch(event(), handlers, None, sink=Recorder(), cap=10000)
    assert len(outcome.stdout) <= 10000
    context = json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context.endswith(TRUNCATION_MARK)


def test_json_escaping_is_charged_to_the_same_budget() -> None:
    handlers = [handler("a", Policy.OPEN, HookResult(context="\n" * 500))]
    outcome = dispatch(event(), handlers, None, sink=Recorder(), cap=200)
    # Each kept `\n` costs two rendered characters once JSON-escaped, so an odd cap budget
    # cannot be spent to the last character: the true optimum here lands one short of the cap,
    # not merely under it, so that is the value to pin instead of an inequality.
    assert len(outcome.stdout) == 199
    context = json.loads(outcome.stdout)["hookSpecificOutput"]["additionalContext"]
    assert context == "\n" * 34 + TRUNCATION_MARK


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
    dispatch(event(tool_input={"command": "rm -rf /"}), handlers, None, sink=Recorder())
    assert seen == ["rm -rf /", "Bash"]


def test_a_handlers_view_keeps_tool_input_aliased_to_raw_like_parse_event_does() -> None:
    # `parse_event` makes `ev.tool_input is ev.raw["tool_input"]` true; the per-handler view
    # must preserve that aliasing, not just isolate handlers from each other, so a handler that
    # writes through `tool_input` and reads back through `raw` sees its own write.
    seen: dict[str, object] = {}

    def write_through_tool_input_read_through_raw(ev: HookEvent, config: object) -> HookResult:
        seen["aliased"] = ev.tool_input is ev.raw["tool_input"]
        ev.tool_input["command"] = "mutated"
        seen["raw_command_after"] = ev.raw["tool_input"]["command"]
        return HookResult()

    handlers = [
        Handler(
            name="a",
            event="PreToolUse",
            policy=Policy.OPEN,
            run=write_through_tool_input_read_through_raw,
        )
    ]
    dispatch(event(tool_input={"command": "ls"}), handlers, None, sink=Recorder())
    assert seen == {"aliased": True, "raw_command_after": "mutated"}


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


def test_the_walk_resolves_a_symlinked_root_the_way_git_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # git resolves a symlink in `cwd` before reporting the toplevel; a walk that returns the
    # unresolved directory it stopped at would report a different `project_root` for the same
    # repository depending on whether it was reached through the real path or a symlink to it.
    real_repo = tmp_path / "realrepo"
    (real_repo / ".git").mkdir(parents=True)
    (real_repo / "sub").mkdir()
    link = tmp_path / "link"
    link.symlink_to(real_repo)
    monkeypatch.setattr("keelline.hooks.dispatch._git_toplevel", _forbidden)
    ev = parse_event({"hook_event_name": "PreToolUse", "cwd": str(link / "sub")}, env={})
    assert ev.project_root == real_repo.resolve()


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
