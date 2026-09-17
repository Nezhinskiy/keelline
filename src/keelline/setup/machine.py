"""Write the machine configuration file, the one both existing readers already read (DP5).

**This module invents no schema.** `config.loader._personal` reads `[personal]` and
`memory.store.overlay_root` reads `[overlay] root`, both with `interactive=False`, and neither
changes here. This writer adds `[machine]` beside them — what `setup` installed, so `doctor`
can check it later — and nothing else. A caller that wants a fourth table is asking for a third
reader of this file, which is out of scope for this plan by the same rule.

**A rewrite merges, table by table, key by key.** `setup` runs again on a machine that already
has a file, and the common case is "set the personal languages, leave the overlay alone" or the
reverse — `overlay_root=None` means *this call does not know*, not *forget what was recorded*,
so an unset value is read back off the existing file before anything is written. The three
tests this file exists to satisfy are the three ways that can go wrong: nothing recorded stays
nothing recorded, a value nobody touched survives a rewrite that touched something else, and one
table's `root` never collapses into a fourth state (see `memory.store.overlay_root`'s own
docstring on that).

**`fsops.write_atomically` on a bare `Path`, not `fsops.write_within`.** Every other writer in
this plan owns a root — a project checkout, the overlay — and walks into it with `O_NOFOLLOW`.
This file has no such root: `config.machine.machine_config_path` resolves to
`~/.config/keelline/config.toml` or wherever `--machine`/`KEELLINE_CONFIG`/`XDG_CONFIG_HOME`
sends it, and that directory is not one this process was handed as "the thing to stay inside
of". `fsops.write_atomically`'s own docstring names exactly this caller: "for callers that
already hold a trusted absolute path". The path is trusted because it is built out of fixed
strings this module and `config.machine` wrote (`"keelline"`, `"config.toml"`) or a path the
machine owner typed on their own command line — never a segment a repository chose, which is
what `mkdirs_within`'s containment exists to stop.

Every string that reaches `tomlout.dumps` is repository-*adjacent* rather than
repository-authored — the overlay root and the personal languages are values the machine owner
typed — but it goes through the one serialiser anyway: `tomlout`'s own docstring says why a
second writer, hand-rolled for "just this one path", is the mistake this module exists to not
repeat.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from keelline import fsops, tomlout

# The one machine-scope settings file this plan writes, relative to `home` (Task 13, Task 15's
# `hook-entries` check). Codex has no equivalent: §5.4's "no `userConfig` in Codex" is one of
# the clauses §10 marks *unmeasured*, so nothing is written there and the report says so rather
# than guessing a path.
USER_SETTINGS = ".claude/settings.json"


@dataclass(frozen=True)
class Written:
    """What `write_machine` wrote. `path` is the file, for a caller that wants to say where."""

    path: Path


def read_machine(path: Path) -> dict[str, Any]:
    """The machine file as a raw `dict`, exactly as `tomllib` parses it."""
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _existing(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return read_machine(path)


def _table(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    return dict(value) if isinstance(value, dict) else {}


def write_machine(
    path: Path,
    *,
    personal: Mapping[str, object],
    overlay_root: Path | None,
    machine: Mapping[str, object],
) -> Written:
    """Merge `personal`, `overlay_root` and `machine` into the file at `path`, and write it.

    Each of the three is merged over what the file already holds, key by key, rather than
    replacing its table outright — a second `setup` run that only sets one of them must not
    erase what an earlier run recorded (DP5, and the test this docstring's module comment
    names). `overlay_root=None` reads as "not given this run": the existing `[overlay] root`,
    if any, is carried over unchanged. There is no way to ask this function to *clear* a
    recorded overlay root; nothing in this plan needs one.
    """
    existing = _existing(path)
    tables: dict[str, dict[str, object]] = {}

    merged_personal = {**_table(existing, "personal"), **personal}
    if merged_personal:
        tables["personal"] = merged_personal

    root = overlay_root
    if root is None:
        recorded = _table(existing, "overlay").get("root")
        if isinstance(recorded, str) and recorded:
            root = Path(recorded)
    if root is not None:
        tables["overlay"] = {"root": str(root)}

    merged_machine = {**_table(existing, "machine"), **machine}
    if merged_machine:
        tables["machine"] = merged_machine

    fsops.write_atomically(path, tomlout.dumps(tables))
    return Written(path)
