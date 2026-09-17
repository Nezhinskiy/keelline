"""What attaching would add to this project's local settings, and where it may read it from.

**Two sources, and the third one is the defect.** The inputs are `<overlay>/common/claude/` and
`<overlay>/projects/<name>/claude/` — the machine owner's own files, in the repository the
machine file anchors. `.claude/settings.json` is read for *nothing*: it is committed, so it is
repository-controlled, and §3's last row and §12 both say it in one line — "Committed settings
widen permissions → never merged". `.claude/settings.local.json` is read, and only to subtract:
a rule the project already carries is not something this attach would add.

**The two halves of the diff are not symmetric (DP4).** A hook entry carries `# keelline:<id>`
inside its command string, so it has an in-band witness that survives the file being edited by
hand — `scaffold.owned_ids` reads them back. A `permissions.allow` string cannot carry one:
`scaffold.mark` appends to a *command*, and `scaffold.entries.unmarked` walks
`groups → hooks → command`. So an allow rule has exactly one witness, the ledger `write.py`
keeps, and this module numbers hook ids per entry rather than sharing one — `owned_ids` is a
`dict[str, str]`, so one id for N entries yields one provenance row and the same id under two
events keeps only the last.

**What may be printed.** `added_allow` and `added_hooks` are built out of the overlay, which is
the owner's own repository, so a command may show them — and must, since a diff nobody reads is
not a gate. `already_present` comes out of `.claude/settings.local.json`, which a hostile clone
*can* commit, so it is repository-authored: this module carries the strings so a caller can
subtract with them, and `check` reports only how many there were.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from keelline.attach.binding import MISMATCH, Binding, read_binding
from keelline.errors import Failure
from keelline.memory.api import PROJECTS
from keelline.overlay.api import COMMON_CLAUDE
from keelline.result import Result
from keelline.scaffold import EntriesError, mark

# The project-local file `attach` owns outright (DP4). `.claude/settings.json` beside it is the
# committed one and is never read.
LOCAL_SETTINGS = ".claude/settings.local.json"
PERMISSIONS_FILE = "permissions.json"
HOOKS_FILE = "hooks.json"
# The per-harness subdirectory of a project's own share of the overlay.
PROJECT_CLAUDE = "claude"
PROJECT_CODEX = "codex"
# `keelline:overlay-<event>-<n>`: one id per entry, for the reason in the module docstring.
ENTRY_PREFIX = "overlay"


@dataclass(frozen=True)
class PermissionDiff:
    """What `attach` would add, and what is already there.

    `added_hooks` holds the *marked* command strings, which is what a reader has to see: the
    marker is the key the merge is done on, and an entry whose marker changed is a different
    entry however familiar its command looks.
    """

    added_allow: tuple[str, ...]
    added_hooks: tuple[str, ...]
    already_present: tuple[str, ...]

    @property
    def widens(self) -> bool:
        """Whether applying this diff would grant a capability the project does not have.

        The gate DP3 puts on the write is on *this*, not on the command: an overlay with no
        allow rules and no hook entries — the state of a freshly created one — must still link
        memory with no flag, or the flag becomes something people pass reflexively.
        """
        return bool(self.added_allow or self.added_hooks)


def _object(text: str, label: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EntriesError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise EntriesError(f"{label} is not a JSON object")
    return raw


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise Failure(f"{path} cannot be read: {exc}") from exc


def _allow_rules(path: Path) -> tuple[str, ...]:
    """The `permissions.allow` list of one settings-shaped document, or nothing."""
    permissions = _object(_read(path), str(path)).get("permissions")
    if not isinstance(permissions, dict):
        return ()
    allow = permissions.get("allow")
    if not isinstance(allow, list):
        return ()
    return tuple(rule for rule in allow if isinstance(rule, str))


def _hook_groups(path: Path) -> dict[str, list[dict[str, Any]]]:
    """`event -> groups` out of a `hooks.json`-shaped document, refusing a shape it cannot read.

    A shape this cannot read is a refusal and never a filter, for `scaffold.entries`' own
    reason: what is dropped silently here is an entry the owner put in their overlay on
    purpose, and nothing would say it never arrived.
    """
    hooks = _object(_read(path), str(path)).get("hooks", {})
    if not isinstance(hooks, dict):
        raise EntriesError(f"{path}: 'hooks' is not an object")
    found: dict[str, list[dict[str, Any]]] = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list) or not all(isinstance(g, dict) for g in groups):
            raise EntriesError(f"{path}: 'hooks.{event}' is not a list of entry groups")
        found[str(event)] = [dict(g) for g in groups]
    return found


def _claude_sources(binding: Binding, name: str) -> tuple[Path, Path]:
    """The two per-harness files this diff reads, common first, this project's second."""
    return (
        binding.overlay / COMMON_CLAUDE / name,
        binding.overlay / PROJECTS / binding.project / PROJECT_CLAUDE / name,
    )


def overlay_entries(binding: Binding) -> dict[str, list[dict[str, Any]]]:
    """The hook entries the overlay would install, each command carrying its own marker id.

    Shaped exactly as `scaffold.apply_entries` wants its `wanted` argument, because that is the
    merge — this lane does not own one. Numbering runs per event across both sources in read
    order, so a second attach against an unchanged overlay produces the identical ids and the
    merge is a no-op.
    """
    wanted: dict[str, list[dict[str, Any]]] = {}
    seen: dict[str, int] = {}
    for source in _claude_sources(binding, HOOKS_FILE):
        for event, groups in _hook_groups(source).items():
            for group in groups:
                entries = group.get("hooks") or []
                if not isinstance(entries, list):
                    raise EntriesError(f"{source}: an entry group's 'hooks' is not a list")
                marked: list[dict[str, Any]] = []
                for entry in entries:
                    command = entry.get("command") if isinstance(entry, dict) else None
                    if not isinstance(command, str):
                        raise EntriesError(f"{source}: an entry under {event} has no command")
                    seen[event] = seen.get(event, 0) + 1
                    entry_id = f"{ENTRY_PREFIX}-{event}-{seen[event]}"
                    marked.append({**entry, "command": mark(command, entry_id)})
                if marked:
                    wanted.setdefault(event, []).append({**group, "hooks": marked})
    return wanted


def local_document(root: Path) -> str:
    """The project's own `settings.local.json`, or an empty string when it has none."""
    return _read(root / LOCAL_SETTINGS)


def _commands(document: str, label: str) -> set[str]:
    """Every hook command already in a settings document, whoever wrote it."""
    hooks = _object(document, label).get("hooks", {})
    if not isinstance(hooks, dict):
        raise EntriesError(f"{label}: 'hooks' is not an object")
    found: set[str] = set()
    for groups in hooks.values():
        for group in groups if isinstance(groups, list) else []:
            entries = group.get("hooks") if isinstance(group, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                command = entry.get("command") if isinstance(entry, dict) else None
                if isinstance(command, str):
                    found.add(command)
    return found


def diff_permissions(root: Path, binding: Binding) -> PermissionDiff:
    """What attaching `binding` would add to `root`, without writing a byte."""
    overlay_common, overlay_project = _claude_sources(binding, PERMISSIONS_FILE)
    # The whole of §12's "committed settings widen permissions → never merged": the committed
    # `.claude/settings.json` sits one name away from both of these and is not on this line.
    sources = (overlay_common, overlay_project)
    granted = [rule for source in sources for rule in _allow_rules(source)]
    document = local_document(root)
    held = set(_allow_rules(root / LOCAL_SETTINGS))
    present = _commands(document, LOCAL_SETTINGS)
    added_allow = tuple(dict.fromkeys(rule for rule in granted if rule not in held))
    already = tuple(dict.fromkeys(rule for rule in granted if rule in held))
    added_hooks = tuple(
        entry["command"]
        for groups in overlay_entries(binding).values()
        for group in groups
        for entry in group["hooks"]
        if entry["command"] not in present
    )
    return PermissionDiff(added_allow, added_hooks, already)


def check(root: Path, *, store: Path, machine: Path | None) -> Result:
    """`attach --check`: the binding and the diff, with nothing written.

    Here rather than in `binding.py` because it needs both halves and `permissions` already
    imports `binding`; the other way round is a cycle.

    Exit 1 on a `mismatch` — a finding, not a refusal, because the answer is "ask the owner"
    and `attach` itself is what refuses. Neither remote reaches the output: both are
    repository-authored, and the state label this lane computed says everything a reader needs.
    """
    binding = read_binding(root, store=store, machine=machine)
    diff = diff_permissions(root, binding)
    summary = (
        f"{binding.project}: {binding.state}; "
        f"{len(diff.added_allow)} allow rule(s) and {len(diff.added_hooks)} hook entr(ies) "
        f"would be added, {len(diff.already_present)} already present"
    )
    data = {
        "project": binding.project,
        "state": binding.state,
        "added_allow": list(diff.added_allow),
        "added_hooks": list(diff.added_hooks),
        # A count and not the strings: this list comes out of the project's own
        # `settings.local.json`, which a clone can commit, so it is repository-authored.
        "already_present": len(diff.already_present),
        "widens": diff.widens,
    }
    return Result(summary, data, exit_code=1 if binding.state == MISMATCH else 0)
