"""Discovery owns the event vocabulary, so a mistyped event is not a silent no-op."""

from __future__ import annotations

import pytest

from keelline.hooks.api import EVENTS, Handler, HookEvent, HookResult, Policy
from keelline.hooks.registry import UnknownHookEvent, discover


class Area:
    """Stands in for `keelline.<area>.hooks`, which no shipped area provides yet."""

    def __init__(self, name: str, handlers: list[Handler]) -> None:
        self.__name__ = name
        self._handlers = handlers

    def register(self) -> list[Handler]:
        return self._handlers


def guard(event: str) -> Handler:
    def run(ev: HookEvent, config: object) -> HookResult:
        return HookResult()

    return Handler(name="background-cleanup", event=event, policy=Policy.CLOSED, run=run)


def area_of(monkeypatch: pytest.MonkeyPatch, *handlers: Handler) -> None:
    area = Area("keelline.lane.hooks", list(handlers))
    monkeypatch.setattr("keelline.hooks.registry.area_modules", lambda submodule: [area])


def test_a_mistyped_event_name_is_refused_and_named(monkeypatch: pytest.MonkeyPatch) -> None:
    area_of(monkeypatch, guard("PreToolUSe"))
    with pytest.raises(UnknownHookEvent) as raised:
        discover()
    message = str(raised.value)
    assert "keelline.lane.hooks" in message
    assert "'background-cleanup'" in message
    assert "'PreToolUSe'" in message


def test_a_handler_on_a_known_event_registers_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = guard("PreToolUse")
    area_of(monkeypatch, handler)
    assert discover() == [handler]


def test_the_vocabulary_is_the_five_events_the_design_table_carries() -> None:
    # A lane that needs a sixth adds it to EVENTS deliberately; widening it by accident is
    # what turns a mistyped handler back into a guard that never fires.
    assert EVENTS == (
        "SessionStart",
        "UserPromptSubmit",
        "UserPromptExpansion",
        "PreToolUse",
        "PostToolUse",
    )
