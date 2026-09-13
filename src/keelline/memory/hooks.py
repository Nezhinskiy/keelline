"""Handlers this area contributes; `hooks-core` owns the entries that invoke them (C4, §5.3).

Every import of `keelline.config`, `keelline.memory.store` and their neighbours happens
**inside** a handler body. `tests/test_areas.py` asserts that `discover()` in a clean
interpreter imports neither the configuration layer nor the presets, and discovery imports
every area's `hooks` module — so a module-level `from keelline.config.schema import Config`
here reddens a test that belongs to no wave-2 lane. The annotation is a string under
`TYPE_CHECKING`, exactly as `keelline.hooks.api` already writes it.

There is no `SessionStart` context handler here, and that absence is the design: the four
injection bundles are invoked as their own `hooks.json` entries so each gets its own platform
cap (see `bundles`). What remains is the one thing that must happen before any of them can
work — linking the store into a worktree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from keelline.hooks.api import Handler, HookEvent, HookResult, Policy

if TYPE_CHECKING:
    from keelline.config.schema import Config


def _link_worktree(event: HookEvent, config: Config | None) -> HookResult:
    if config is None or event.project_root is None:
        return HookResult()
    try:
        from keelline.memory.store import resolve
        from keelline.memory.worktree import link

        store = resolve(event.project_root, config)
        if store is None:
            from keelline.memory.store import refusal_reason

            reason = refusal_reason(event.project_root, config)
            return HookResult(context=f"keelline: no memory store — {reason}" if reason else None)
        created = link(event.project_root, store, config)
        if not created:
            return HookResult()
        return HookResult(
            context=f"keelline: linked {len(created)} memory path(s) into this worktree"
        )
    except Exception:  # a memory handler never costs a session (§5.3)
        return HookResult()


def register() -> list[Handler]:
    return [
        Handler(
            name="worktree-link",
            event="SessionStart",
            policy=Policy.OPEN,
            run=_link_worktree,
        )
    ]
