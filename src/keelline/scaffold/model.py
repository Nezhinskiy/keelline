"""What a consumer asks for, and what the engine answers (contract C2).

`Template` is a description, not a file: the lanes that own template *content*
(`templates/`, `overlay/`) build these, and this lane never reads the plugin's own directory.
That is what keeps the engine testable without shipping any template at all.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from keelline.scaffold.manifest import Kind, Record
from keelline.scaffold.regions import Style


class Verb(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    SKIP_MODIFIED = "skip_modified"
    REMOVE = "remove"
    REGION_UPDATE = "region_update"
    ENTRIES_UPDATE = "entries_update"


WRITING = frozenset({Verb.CREATE, Verb.UPDATE, Verb.REGION_UPDATE, Verb.ENTRIES_UPDATE})


@dataclass(frozen=True)
class Template:
    id: str
    kind: Kind
    target: str
    source: str
    render: Callable[[], str]
    region: str | None = None
    style: Style = Style.MARKDOWN
    entries: dict[str, list[dict[str, Any]]] | None = None
    retired: bool = False


@dataclass(frozen=True)
class Action:
    verb: Verb
    artifact_id: str
    target: str
    payload: str | None
    reason: str
    record: Record | None


@dataclass(frozen=True)
class Refused:
    artifact_id: str
    target: str
    reason: str


@dataclass(frozen=True)
class Plan:
    actions: list[Action] = field(default_factory=list)
    refusals: list[Refused] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def writes(self) -> list[str]:
        return [
            action.target
            for action in self.actions
            if action.verb in WRITING or action.verb is Verb.REMOVE
        ]


@dataclass(frozen=True)
class Applied:
    written: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
