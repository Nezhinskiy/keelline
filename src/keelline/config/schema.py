"""Typed sections of keelline.toml. Numbers come from the preset, never from code."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

# The future import above is load-bearing for the loader: it turns every annotation here into
# a string, which `config.loader._schema_types` resolves with `typing.get_type_hints` to decide
# how to coerce a value. Every name an annotation uses must stay resolvable from this module's
# globals at runtime, so a type imported only under `TYPE_CHECKING` would break the loader.

# The one grammar for a name Keelline answers to: a project, a profile, an overlay owner, a
# custom gate. Each is one lowercase path segment whose leading class keeps it out of an option's
# position in an argv. Every other module derives from this spelling rather than keeping its own.
PROJECT_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*\Z")
# The grammar a `[paths]` value must match before it may be printed anywhere; `contained()`
# decides whether it may be written, and a shape rule cannot bound a charset.
#
# The segment shape is part of the grammar because the two readers of a path have to agree about
# what a path is. A charset alone admitted `docs//x.md`, `docs/x/` and `./docs`: `contained()`
# read them through `Path(relative).parts`, which drops an empty component, a trailing slash and
# a leading `./` without a word, so `plan()` reported no refusal — while `fsops` splits the raw
# string and refuses all three, so `apply()` raised part-way through a pass that had already put
# earlier artifacts on disk and whose `finally` had already persisted the manifest. The value
# was never writable; only the two spellings of "a path" disagreed about saying so.
#
# So the grammar is written per segment: exactly one `/` between segments, no segment empty, and
# the lookahead per segment because the charset alone cannot say it. `.` and `..` are spelled
# entirely out of the charset the segments already use, so a segment rule without the lookahead
# admits `./docs`, `docs/../x` and `..` itself — measured, on the charset-plus-segments form this
# started from. `.hidden` and `..foo` are ordinary names and stay admitted: the lookahead refuses
# a segment that is one or two dots *and nothing else*. What is left is exactly the set
# `fsops.checked_components` accepts, intersected with the charset, and `contained()` asks that
# function for the component rule rather than keeping a second copy of it.
PATH_VALUE = re.compile(
    r"^(?!\.\.?(?:/|\Z))[A-Za-z0-9._][A-Za-z0-9._-]*(?:/(?!\.\.?(?:/|\Z))[A-Za-z0-9._-]+)*\Z"
)
# The grammar an unknown *name* in a `keelline.toml` must match before a refusal may print it —
# a top-level section's, and a key's inside a known table. Both are repository-authored the same
# way a `[paths]` value is, and both of the loader's refusals echoed them back whole, newlines
# and all (P10, fix round 1, finding 2; the key half, round 2). A TOML key is arbitrary quoted
# text, so the two are one grammar and not two: every name Keelline itself answers to — every
# schema field, every `Budgets.NAMES` entry, every section — is lowercase words joined by
# underscores, and anything else is counted rather than quoted.
SECTION_NAME = re.compile(r"^[a-z][a-z_]*\Z")
STATES = ("initialised", "adopting", "installed")
# The built-in gates, in the order every report lists them. `[gates] builtin` chooses among them
# and `[gates.custom]` adds a project's own. The loader needs the names without importing an
# area, which is why they live here; the area that runs them pins its objects to this tuple.
BUILTIN_GATES = ("docs", "bugs", "plan", "commit", "trail")
# The configuration check: a gate runner's other verdict, and never a gate's name.
CONFIG_CHECK = "config"
MEMORY_MODES = ("overlay", "in-repo", "local-only")
CI_MODES = ("reusable", "uvx", "none")


@dataclass(frozen=True)
class Keelline:
    version: str
    state: str
    preset: str
    profile: str
    agents: tuple[str, ...]
    enforced: tuple[str, ...]

    @property
    def enforcing(self) -> frozenset[str]:
        """The gates that fail a run rather than annotate it.

        `enforced` as loaded, which under `installed` the loader has already filled with every
        configured gate: `installed` meant "every gate enforces" before the list existed, and a
        document written then says nothing else.

        No command reads it in this release. It is the one reading of "which gates enforce"
        for `keelline gate` and `keelline assess`, which ship later and each ask it per gate;
        a lane that read `enforced` directly would skip the loader's `installed` rule.
        """
        return frozenset(self.enforced)


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
    keelline: str

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
class CustomGate:
    """A project's own gate: an argv run from the project root, never a shell string."""

    run: tuple[str, ...]


@dataclass(frozen=True)
class Gates:
    """`[gates]`: which built-in gates run, and the project's own.

    `custom` has a default because the loader fills it itself, table by table, after `_build`
    has held the rest; it is the one schema field `_build` leaves out when it is absent.
    """

    builtin: tuple[str, ...]
    custom_timeout_seconds: int
    custom: Mapping[str, CustomGate] = field(default_factory=dict)


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
    gates: Gates
    commit_messages: CommitMessages
    personal: Personal

    @property
    def gate_names(self) -> tuple[str, ...]:
        """The gates this project runs: its built-ins in `BUILTIN_GATES` order, then its own."""
        kept = tuple(name for name in BUILTIN_GATES if name in self.gates.builtin)
        return kept + tuple(sorted(self.gates.custom))
