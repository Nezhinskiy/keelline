from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from keelline.config.schema import Config


# The five events §5.3's table carries. A lane that needs a sixth adds it here deliberately;
# `registry.discover` refuses anything else, so a handler registered for "PreToolUSe" is a
# loud failure at discovery rather than a guard that never fires and tests that never notice.
EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "PreToolUse",
    "PostToolUse",
)


class Policy(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Decision(StrEnum):
    DENY = "deny"


@dataclass(frozen=True)
class HookEvent:
    name: str
    session_id: str | None
    agent_id: str | None
    tool_name: str | None
    tool_input: dict[str, Any]
    cwd: Path
    project_root: Path | None
    harness: str
    raw: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass
class HookResult:
    context: str | None = None
    decision: Decision | None = None
    reason: str | None = None


HandlerFn = Callable[[HookEvent, "Config | None"], HookResult]


@dataclass(frozen=True)
class Handler:
    name: str
    event: str
    policy: Policy
    run: HandlerFn
    # Handlers stay pure `(event, config) -> result` (§5.3), so a handler that must run once
    # per context declares the marker key and the dispatcher owns the bookkeeping.
    once_key: str | None = None


class Sink(Protocol):
    """Where the dispatcher records failures and once-per-context markers (§5.3)."""

    def diagnostic(self, record: dict[str, object]) -> None: ...

    def seen(self, key: str) -> bool: ...

    def mark(self, key: str) -> None: ...


class NullSink:
    """A sink that forgets rather than suppresses.

    `seen()` is always False, so `once_key` degrades from "once per context" to "every
    invocation" and every diagnostic is discarded.

    The durable, session-keyed sink now exists — `keelline.hooks.sink.sink_for` — and this is
    what it answers when there is nowhere to write: no harness data root, or one this process
    cannot write to. So this is the *degradation*, not the shipped default, and a handler whose
    work must genuinely happen once still cannot rely on `once_key` alone, because the
    degradation is a state any machine can be in.
    """

    def diagnostic(self, record: dict[str, object]) -> None:
        return None

    def seen(self, key: str) -> bool:
        return False

    def mark(self, key: str) -> None:
        return None
