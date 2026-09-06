"""Typed sections of keelline.toml. Numbers come from the preset, never from code."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar

PROJECT_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
STATES = ("initialised", "adopting", "installed")
MEMORY_MODES = ("overlay", "in-repo", "local-only")
CI_MODES = ("reusable", "uvx", "none")


@dataclass(frozen=True)
class Keelline:
    version: str
    state: str
    preset: str
    profile: str
    agents: tuple[str, ...]


@dataclass(frozen=True)
class Project:
    name: str
    base_branch: str
    release_branch: str


@dataclass(frozen=True)
class Paths:
    agents_md: str
    architecture: str
    runbooks: str
    adr: str
    specs: str
    plans: str
    bugs: str
    bug_index: str
    roadmap: str
    roadmap_history: str
    memory: str

    def as_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class Memory:
    mode: str
    groups: tuple[str, ...]
    index_extra: tuple[str, ...]


@dataclass(frozen=True)
class Budgets:
    """A project may lower a budget below the preset and never raise it (D7)."""

    NAMES: ClassVar[tuple[str, ...]] = (
        "agents_md_lines",
        "agents_md_words",
        "status_lines",
        "roadmap_prose_lines",
        "roadmap_prose_words",
        "memory_index_words",
        "startup_rules_words",
        "volatile_notes_words",
        "volatile_ttl_days",
    )

    preset: dict[str, int]
    configured: dict[str, int] = field(default_factory=dict)

    def effective(self, name: str) -> int:
        if name not in self.NAMES:
            raise KeyError(name)
        value = self.preset[name]
        if name in self.configured:
            value = min(value, self.configured[name])
        return value

    @property
    def overrides(self) -> dict[str, int]:
        return {k: v for k, v in self.configured.items() if v != self.preset.get(k)}


@dataclass(frozen=True)
class NativeCaps:
    """Platform limits in their own units; consumers of a bounded thing read them (§9.5)."""

    NAMES: ClassVar[tuple[str, ...]] = (
        "memory_index_lines",
        "memory_index_bytes",
        "hook_output_chars",
    )

    memory_index_lines: int
    memory_index_bytes: int
    hook_output_chars: int


@dataclass(frozen=True)
class Ledger:
    id_prefix: str
    code_roots: tuple[str, ...]
    evidence_boundary_required_for: tuple[str, ...]


@dataclass(frozen=True)
class Artifacts:
    local: tuple[str, ...]


@dataclass(frozen=True)
class Ci:
    mode: str
    ref: str
    gate_branch: str


@dataclass(frozen=True)
class CommitMessages:
    attribution_check: bool
    types: tuple[str, ...]


@dataclass(frozen=True)
class Personal:
    """Machine-level parameters (§5.4); never read from a repository."""

    reply_language: str
    artifact_language: str
    preset: str


@dataclass(frozen=True)
class Config:
    keelline: Keelline
    project: Project
    paths: Paths
    memory: Memory
    budgets: Budgets
    native_caps: NativeCaps
    ledger: Ledger
    artifacts: Artifacts
    ci: Ci
    commit_messages: CommitMessages
    personal: Personal
