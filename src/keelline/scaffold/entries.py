"""Keyed entries inside a settings file a person and several tools share (§7.2).

Keying on a marker inside the command string rather than on position is what lets `upgrade`
replace what Keelline installed while a foreign entry beside it — another plugin's, or the
owner's own — survives untouched and stays visible to `doctor`.

Two rules make "foreign entries untouched" true rather than approximately true. A group that
mixes a marked entry with an unmarked one is **split**, not replaced: the unmarked half keeps
its matcher and its position. And what the manifest stamps is `owned(document)` — the marked
entries alone — never the whole file, so a user adding a `permissions` block beside the hooks
does not freeze Keelline's own entries forever.
"""

from __future__ import annotations

import json
import re
from typing import Any

from keelline.errors import Refusal

ENTRY_MARKER = "# keelline:"
_MARKER = re.compile(r"#\s*keelline:([A-Za-z0-9][A-Za-z0-9._-]*)\s*$")


class EntriesError(Refusal):
    """A settings document the engine cannot rewrite without guessing."""


def marker_id(command: str) -> str | None:
    match = _MARKER.search(command)
    return match.group(1) if match else None


def mark(command: str, entry_id: str) -> str:
    if marker_id(command) == entry_id:
        return command
    return f"{command}  {ENTRY_MARKER}{entry_id}"


def _load(document: str) -> dict[str, Any]:
    if not document.strip():
        return {}
    try:
        raw = json.loads(document)
    except json.JSONDecodeError as exc:
        raise EntriesError(f"settings document is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise EntriesError("settings document is not a JSON object")
    return raw


def _hooks_table(raw: dict[str, Any]) -> dict[str, Any]:
    hooks = raw.get("hooks", {})
    if not isinstance(hooks, dict):
        raise EntriesError("'hooks' is not an object")
    return hooks


def _groups(raw: dict[str, Any], event: str) -> list[dict[str, Any]]:
    groups = _hooks_table(raw).get(event, [])
    if not isinstance(groups, list):
        raise EntriesError(f"'hooks.{event}' is not a list")
    return [group for group in groups if isinstance(group, dict)]


def _entries_of(group: dict[str, Any]) -> list[dict[str, Any]]:
    entries = group.get("hooks", [])
    return (
        [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []
    )


def _claimed(entry: dict[str, Any]) -> str | None:
    command = entry.get("command")
    return marker_id(command) if isinstance(command, str) else None


def _without_marked(group: dict[str, Any]) -> dict[str, Any] | None:
    """The group with Keelline's own entries removed, or `None` when nothing foreign is left."""
    kept = [entry for entry in _entries_of(group) if _claimed(entry) is None]
    if not kept:
        return None
    return {**group, "hooks": kept}


def owned_ids(document: str) -> dict[str, str]:
    """Every id Keelline claims in this document, mapped to its event — `doctor`'s provenance."""
    raw = _load(document)
    return {
        claimed: event
        for event in _hooks_table(raw)
        for group in _groups(raw, event)
        for entry in _entries_of(group)
        if (claimed := _claimed(entry)) is not None
    }


def owned(document: str) -> str:
    """A canonical rendering of only the entries Keelline claims — what the manifest stamps."""
    raw = _load(document)
    claimed: dict[str, list[dict[str, Any]]] = {}
    for event in sorted(_hooks_table(raw)):
        for group in _groups(raw, event):
            mine = [entry for entry in _entries_of(group) if _claimed(entry) is not None]
            if mine:
                claimed.setdefault(event, []).append({**group, "hooks": mine})
    return json.dumps(claimed, indent=2, sort_keys=True)


def apply_entries(document: str, wanted: dict[str, list[dict[str, Any]]]) -> str:
    raw = _load(document)
    hooks = dict(_hooks_table(raw))
    for event in sorted(set(hooks) | set(wanted)):
        foreign = [kept for group in _groups(raw, event) if (kept := _without_marked(group))]
        merged = foreign + list(wanted.get(event, []))
        if merged:
            hooks[event] = merged
        else:
            hooks.pop(event, None)
    if hooks:
        raw["hooks"] = hooks
    else:
        raw.pop("hooks", None)
    return json.dumps(raw, indent=2) + "\n"
