"""Run the handlers registered for an event and own the exit code and output shape."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    """A sink that keeps records in memory; tests and `doctor --dry-run` use it."""

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


def parse_event(payload: dict[str, Any], env: Mapping[str, str]) -> HookEvent:
    cwd = Path(str(payload.get("cwd") or "."))
    root_var = env.get("CLAUDE_PROJECT_DIR")
    project_root = Path(root_var) if root_var else _git_toplevel(cwd)
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
        project_root=project_root,
        harness=detect_harness(env, payload),
        raw=payload,
    )


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
        try:
            result = handler.run(event, config)
        except (Exception, SystemExit) as exc:  # judged by the handler's own policy
            reasons.append(f"{handler.name}: {type(exc).__name__}: {exc}")
            sink.diagnostic(
                {"event": event.name, "handler": handler.name, "error": type(exc).__name__}
            )
            refuse = refuse or handler.policy == Policy.CLOSED
            continue
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
    if cap is not None and len(context) > cap:
        context = context[: max(cap - len(TRUNCATION_MARK), 0)] + TRUNCATION_MARK
        context = context[:cap]
        sink.diagnostic({"event": event.name, "handler": "*", "error": "context-truncated"})
    payload: dict[str, Any] = {"hookSpecificOutput": {"hookEventName": event.name}}
    if context:
        payload["hookSpecificOutput"]["additionalContext"] = context
    return Outcome(0, json.dumps(payload), stderr, None)
