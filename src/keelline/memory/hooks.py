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

Nothing a repository controls is ever put into `HookResult.context`. That field becomes
`additionalContext` in the `SessionStart` payload — model input with no delimiter, no nonce, no
trust record and no `may_inject` gate, which is precisely the channel `trust.wrap` exists to
close. `store.refusal_reason` builds its message out of raw `memory.groups` entries, and
`memory.groups` is an ordinary `keelline.toml` list with no schema constraint (a TOML
multi-line string carries literal newlines), so a clone reaches that text with no overlay and
no confirmation. A session-start diagnostic does not need to reach the model at all: the
message below is fixed and repository-independent, and the detail stays where a person reads
it, in the `memory` commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from keelline.hooks.api import Handler, HookEvent, HookResult, Policy

if TYPE_CHECKING:
    from keelline.config.schema import Config

# Fixed, and carrying nothing the repository chose. A plain string is not an import, so
# this costs `discover()` nothing.
NO_STORE = "keelline: no memory store for this project"


def _link_worktree(event: HookEvent, config: Config | None) -> HookResult:
    if config is None or event.project_root is None:
        return HookResult()
    try:
        from keelline.memory.store import resolve
        from keelline.memory.worktree import link

        store = resolve(event.project_root, config)
        if store is None:
            return HookResult(context=NO_STORE)
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
