"""Run the handlers registered for an event and own the exit code and output shape."""

from __future__ import annotations

import copy
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from keelline.hooks.api import Decision, Handler, HookEvent, NullSink, Policy, Sink

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


def detect_harness(env: Mapping[str, str], payload: Mapping[str, Any] | None = None) -> str:
    # S1 (spike record): Codex sets PLUGIN_ROOT/PLUGIN_DATA and ALSO CLAUDE_PLUGIN_ROOT, so
    # the CLAUDE_* names alone identify nothing; Codex's SessionStart stdin also carries
    # `model` and `permission_mode`, which Claude Code's does not.
    if "PLUGIN_ROOT" in env:
        return "codex"
    if payload is not None and {"model", "permission_mode"} <= set(payload):
        return "codex"
    if "CLAUDE_PLUGIN_ROOT" in env or "CLAUDE_PROJECT_DIR" in env:
        return "claude"
    return "unknown"


def _git_toplevel(cwd: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    top = completed.stdout.strip()
    return Path(top) if completed.returncode == 0 and top else None


def _walk_to_git_root(cwd: Path) -> Path | None:
    """`.git` is a directory in a clone and a file in a worktree or a submodule; both count."""
    if not cwd.is_absolute():
        return None
    for directory in [cwd, *cwd.parents]:
        if (directory / ".git").exists():
            return directory
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


def dispatch(
    event: HookEvent,
    handlers: list[Handler],
    config: Config | None,
    *,
    sink: Sink | None = None,
    cap: int | None = None,
) -> Outcome:
    sink = sink or NullSink()
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
            # handler gets its own deep copy of the mutable views instead.
            view = replace(
                event,
                tool_input=copy.deepcopy(event.tool_input),
                raw=copy.deepcopy(event.raw),
            )
            result = handler.run(view, config)
        except (Exception, SystemExit) as exc:  # judged by the handler's own policy
            reasons.append(f"{handler.name}: {type(exc).__name__}: {exc}")
            sink.diagnostic(
                {"event": event.name, "handler": handler.name, "error": type(exc).__name__}
            )
            refuse = refuse or handler.policy == Policy.CLOSED
            continue
        if handler.once_key is not None:
            sink.mark(handler.once_key)
        if result.context:
            contexts.append(result.context)
        if result.decision == Decision.DENY:
            reasons.append(f"{handler.name}: {result.reason or 'denied'}")
            refuse = True
        elif result.decision is not None:
            sink.diagnostic(
                {
                    "event": event.name,
                    "handler": handler.name,
                    "error": "unrecognised-decision",
                    "decision": str(result.decision),
                }
            )
    if refuse:
        return Outcome(2, "", "keelline: refused: " + "; ".join(reasons) + "\n", "deny")
    stderr = ("keelline: " + "; ".join(reasons) + "\n") if reasons else ""
    context = "\n\n".join(contexts)
    stdout = render(event.name, context)
    if cap is not None and len(stdout) > cap:
        stdout = _clamp(event.name, context, cap)
        sink.diagnostic({"event": event.name, "handler": "*", "error": "context-truncated"})
    return Outcome(0, stdout, stderr, None)
