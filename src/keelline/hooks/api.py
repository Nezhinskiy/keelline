from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from keelline.config.schema import Config


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


class Sink(Protocol):
    """Where the dispatcher records failures and once-per-context markers (§5.3)."""

    def diagnostic(self, record: dict[str, object]) -> None: ...

    def seen(self, key: str) -> bool: ...

    def mark(self, key: str) -> None: ...


class NullSink:
    def diagnostic(self, record: dict[str, object]) -> None:
        return None

    def seen(self, key: str) -> bool:
        return False

    def mark(self, key: str) -> None:
        return None
