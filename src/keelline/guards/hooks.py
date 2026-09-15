"""Handlers this area contributes; `hooks-core` owns the entries that invoke them (C4, §5.3).

Every import of `keelline.guards.*` and of the configuration layer happens **inside** a
handler body. `tests/test_areas.py` asserts that `discover()` in a clean interpreter imports
neither the configuration layer nor the presets, and discovery imports every area's `hooks`
module — so a module-level import here reddens a test that belongs to no wave-2 lane.

`bg-cleanup` is the one `Policy.CLOSED` handler in the plugin (§5.3: "background-cleanup guard
(closed)"). It does not catch its own exceptions: D11 says a guard for an action with a high
cost of error fails closed, and the dispatcher is what turns an exception from a CLOSED handler
into exit 2 with a reason. `judge` itself returns rather than raises on any string, so what
reaches that policy is a genuine defect, not an unusual command.

Nothing a repository controls is put into `HookResult.context`. The restore hint is built from
the command's own text — model- or user-authored, never repository bytes — and the hygiene
notice (Task 8) carries counts this module computed and fixed sentences, never a path from
`keelline.toml`.

Both handlers are silent without a configuration (§12: "No `keelline.toml` → Plugin hooks
silent"). For the guard that is a design decision, not a degradation: a repository that has
not run `keelline init` is not guarded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from keelline.hooks.api import Decision, Handler, HookEvent, HookResult, Policy

if TYPE_CHECKING:
    from keelline.config.schema import Config

# The matcher both handlers share. Codex reports every shell-routed action as `Bash` too
# (§10, measured), so this one name serves both harnesses.
BASH = "Bash"


def bash_command(event: HookEvent) -> str | None:
    """The command of a Bash call, or None for any other tool or a malformed input."""
    if event.tool_name != BASH:
        return None
    command = event.tool_input.get("command")
    return command if isinstance(command, str) else None


def _bg_cleanup(event: HookEvent, config: Config | None) -> HookResult:
    if config is None:
        return HookResult()
    command = bash_command(event)
    if command is None:
        return HookResult()
    from keelline.guards.bgcleanup import judge

    background = event.tool_input.get("run_in_background") is True
    verdict = judge(command, background=background)
    if verdict.deny is not None:
        return HookResult(decision=Decision.DENY, reason=verdict.deny)
    return HookResult(context=verdict.hint)


def register() -> list[Handler]:
    return [
        Handler(name="bg-cleanup", event="PreToolUse", policy=Policy.CLOSED, run=_bg_cleanup),
    ]
