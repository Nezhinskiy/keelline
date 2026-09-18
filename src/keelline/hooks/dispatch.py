"""Run the handlers registered for an event and own the exit code and output shape."""

from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from keelline.gitenv import GIT_TIMEOUT_SECONDS, scrubbed_env
from keelline.hooks.api import (
    Decision,
    Handler,
    HookEvent,
    HookResult,
    Policy,
    Sink,
    detect_harness,
)

if TYPE_CHECKING:
    from keelline.config.schema import Config

TRUNCATION_MARK = "\n[keelline: context truncated to the platform cap]"


@dataclass(frozen=True)
class Outcome:
    exit_code: int
    stdout: str
    stderr: str
    decision: str | None = None


@dataclass
class Recorder:
    """A sink that keeps its records and markers in memory; the tests use it."""

    records: list[dict[str, object]] = field(default_factory=list)
    marks: set[str] = field(default_factory=set)

    def diagnostic(self, record: dict[str, object]) -> None:
        self.records.append(record)

    def seen(self, key: str) -> bool:
        return key in self.marks

    def mark(self, key: str) -> None:
        self.marks.add(key)


def _git_toplevel(cwd: Path) -> Path | None:
    try:
        # The environment is scrubbed for the same reason `memory.store._git` scrubs it, said
        # there in as many words: "it must be a real git answer, not one an inherited `GIT_DIR`
        # produced". This call did not, and `project_root()` feeds *every* hook decision — so an
        # inherited `GIT_DIR` or `GIT_WORK_TREE` made every handler in the process answer for a
        # different repository than the one the session is in.
        #
        # S603/S607. List form and never `shell=True`, so nothing is re-parsed by a shell.
        # `cwd` is a path this process computed, not a repository value. `git` is resolved
        # through `PATH` on purpose: the machine owner's `git` is the one that must answer.
        completed = subprocess.run(  # noqa: S603 - see the comment above
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env=scrubbed_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    top = completed.stdout.strip()
    return Path(top) if completed.returncode == 0 and top else None


def _walk_to_git_root(cwd: Path) -> Path | None:
    """`.git` is a directory in a clone and a file in a worktree or a submodule; both count.

    `git rev-parse --show-toplevel` resolves symlinks in `cwd` before it reports the toplevel,
    so the walk must too: otherwise the same repository reached through its real path and
    through a symlink to it would report two different `project_root` values where git
    collapses them into one.
    """
    if not cwd.is_absolute():
        return None
    for directory in [cwd, *cwd.parents]:
        if (directory / ".git").exists():
            return directory.resolve()
    return None


def project_root(cwd: Path, env: Mapping[str, str]) -> Path | None:
    """`CLAUDE_PROJECT_DIR`, else a walk for `.git`, else git itself.

    `keelline hook` runs as a subprocess on every tool call, and Codex sets `PLUGIN_ROOT`,
    `PLUGIN_DATA` and `CLAUDE_PLUGIN_ROOT` but no `CLAUDE_PROJECT_DIR` (S1), so the fallback
    is the Codex hot path. `git rev-parse --show-toplevel` costs about 8 ms of a 33 ms
    invocation and the walk about 0.004 ms; git stays behind it for what a walk cannot see,
    such as `GIT_DIR` and a bare repository.
    """
    root_var = env.get("CLAUDE_PROJECT_DIR")
    if root_var:
        return Path(root_var)
    return _walk_to_git_root(cwd) or _git_toplevel(cwd)


def parse_event(payload: dict[str, Any], env: Mapping[str, str]) -> HookEvent:
    cwd = Path(str(payload.get("cwd") or "."))
    tool_input = payload.get("tool_input") or {}
    session_id = payload.get("session_id")
    agent_id = payload.get("agent_id")
    tool_name = payload.get("tool_name")
    return HookEvent(
        name=str(payload.get("hook_event_name") or "unknown"),
        session_id=session_id if isinstance(session_id, str) else None,
        agent_id=agent_id if isinstance(agent_id, str) else None,
        tool_name=tool_name if isinstance(tool_name, str) else None,
        tool_input=tool_input if isinstance(tool_input, dict) else {},
        cwd=cwd,
        project_root=project_root(cwd, env),
        harness=detect_harness(env, payload),
        raw=dict(payload),
    )


def render(event_name: str, context: str) -> str:
    """The whole string a hook writes to stdout; the platform caps this, not the field."""
    payload: dict[str, Any] = {"hookSpecificOutput": {"hookEventName": event_name}}
    if context:
        payload["hookSpecificOutput"]["additionalContext"] = context
    return json.dumps(payload)


def _clamp(event_name: str, context: str, cap: int) -> str:
    """Fit the emitted string, envelope included, inside the cap (§9.5).

    Claude Code caps each hook's output string at 10,000 characters — `additionalContext`,
    `systemMessage` and plain stdout alike — and replaces anything longer with a preview and a
    file path. A bundle truncated to the cap and then wrapped in JSON therefore gets replaced
    while the truncation mark claims it was handled. The envelope's width depends on the event
    name and JSON escaping widens the context itself, so the largest prefix that still fits is
    searched for rather than computed. A cap that leaves no room even for the empty envelope
    emits nothing: an over-cap string would be replaced by a preview anyway.
    """
    best: str | None = None
    low, high = 0, min(len(context), cap)  # a kept character costs at least one of the cap
    while low <= high:
        keep = (low + high) // 2
        stdout = render(event_name, context[:keep] + TRUNCATION_MARK)
        if len(stdout) <= cap:
            best, low = stdout, keep + 1
        else:
            high = keep - 1
    if best is not None:
        return best
    bare = render(event_name, "")
    return bare if len(bare) <= cap else ""


class _UnrecognisedDecision(Exception):
    """A verdict `dispatch` cannot read.

    Raised rather than ignored so it travels the path a handler's exception already travels:
    the handler's own policy judges it, a CLOSED guard that misnames its deny refuses instead
    of permitting, and the reason reaches stderr — which production reads — and not only the
    sink, which today forgets (see `NullSink`).
    """

    def __init__(self, decision: object) -> None:
        super().__init__(f"unrecognised decision {decision!r}")
        self.decision = decision


class _UnrecognisedContext(Exception):
    """A `context` `dispatch` cannot join into the emitted payload.

    `HookResult.context` is typed `str | None`, but nothing stops a dynamically built result
    from carrying something else, and the join that builds the payload happens once, after
    every handler has run — outside every per-handler `try`. Raised inside the per-handler
    `try` instead, so a malformed `context` is that handler failing rather than a `TypeError`
    that takes down the whole dispatch: an OPEN handler's policy swallows it and a CLOSED
    handler's policy refuses, exactly like a malformed decision. Raised *after* the decision
    branch, never before it: a deny already read off the same result is banked first, so a
    handler that denies and carries a malformed context keeps its refusal.
    """

    def __init__(self, context: object) -> None:
        super().__init__(f"unrecognised context {context!r}")
        self.context = context


def _failure(exc: BaseException) -> tuple[str, dict[str, object]]:
    """The stderr reason and the sink record one handler's failure earns."""
    if isinstance(exc, _UnrecognisedDecision):
        return str(exc), {"error": "unrecognised-decision", "decision": str(exc.decision)}
    if isinstance(exc, _UnrecognisedContext):
        return str(exc), {"error": "unrecognised-context", "context": str(exc.context)}
    return f"{type(exc).__name__}: {exc}", {"error": type(exc).__name__}


def dispatch(
    event: HookEvent,
    handlers: list[Handler],
    config: Config | None,
    *,
    sink: Sink,
    cap: int | None = None,
) -> Outcome:
    """One deny travels on one channel — the exit code — so every failure here is judged.

    `sink` carries no default on purpose: a caller that has no durable sink must say so with
    `NullSink()` and inherit its forgetfulness (§5.3), rather than acquire it by omission.
    """
    contexts: list[str] = []
    reasons: list[str] = []
    refuse = False
    for handler in handlers:
        if handler.event != event.name:
            continue
        if handler.once_key is not None and sink.seen(handler.once_key):
            continue
        try:
            # Purity is contractual and unenforceable, and handlers run in name order, so an
            # earlier one could blank `tool_input["command"]` under a later one's guard. Each
            # handler gets its own deep copy of the mutable views instead. `raw` is copied once
            # and `tool_input` is taken from that same copy, so the view keeps the aliasing
            # `parse_event` produces (`ev.tool_input is ev.raw["tool_input"]`) rather than
            # diverging under two independent deep copies.
            raw_view = copy.deepcopy(event.raw)
            raw_tool_input = raw_view.get("tool_input")
            tool_input_view = (
                raw_tool_input
                if isinstance(raw_tool_input, dict)
                else copy.deepcopy(event.tool_input)
            )
            view = replace(event, tool_input=tool_input_view, raw=raw_view)
            result = handler.run(view, config)
            # Consuming the result belongs inside this `try`: reading `.context` off whatever a
            # handler actually returned used to raise out of `dispatch` entirely, so one later
            # handler's malformed return destroyed an earlier handler's deny.
            if not isinstance(result, HookResult):
                raise TypeError(f"returned {type(result).__name__}, not HookResult")
            if handler.once_key is not None:
                sink.mark(handler.once_key)
            # The decision is read before anything else that can fail this handler. A deny is
            # the one thing a neighbouring bug must never cost, and it travels on one channel;
            # banking it here means a malformed `context` on the same result costs that handler
            # its context and a recorded failure, not its refusal. Validating `context` above
            # this branch turned a live deny into an allow, which is the very defect the
            # per-handler judging exists to prevent. The asymmetry with a malformed *decision*
            # is deliberate: there is no well-formed deny to lose there.
            if result.decision == Decision.DENY:
                reasons.append(f"{handler.name}: {result.reason or 'denied'}")
                refuse = True
            elif result.decision is not None:
                raise _UnrecognisedDecision(result.decision)
            # `context` is validated here too, and not only at the join below: the join runs
            # once after every handler, outside every per-handler `try`, so a non-string context
            # caught there would take the whole dispatch down instead of being judged by this
            # handler's own policy.
            if result.context is not None and not isinstance(result.context, str):
                raise _UnrecognisedContext(result.context)
            if result.context:
                contexts.append(result.context)
        except BaseException as exc:  # judged by the handler's own policy
            reason, record = _failure(exc)
            reasons.append(f"{handler.name}: {reason}")
            sink.diagnostic({"event": event.name, "handler": handler.name, **record})
            refuse = refuse or handler.policy == Policy.CLOSED
            continue
    if refuse:
        return Outcome(2, "", "keelline: refused: " + "; ".join(reasons) + "\n", "deny")
    stderr = ("keelline: " + "; ".join(reasons) + "\n") if reasons else ""
    context = "\n\n".join(contexts)
    stdout = render(event.name, context)
    if cap is not None and len(stdout) > cap:
        stdout = _clamp(event.name, context, cap)
        sink.diagnostic({"event": event.name, "handler": "*", "error": "context-truncated"})
    return Outcome(0, stdout, stderr, None)
