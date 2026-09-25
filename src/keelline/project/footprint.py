"""What `init`, `upgrade` and `uninstall` do with the footprint `project_templates` builds, before
the engine plans it.

`project.templates` builds templates from a configuration and decides nothing about a manifest.
This module is the lifecycle policy the three commands apply to what it builds: where
`[artifacts] local` may not move an artifact, which recorded artifacts a configuration retires,
and the order of the footprint pass. `prepare` applies all of it in one sequence, because the
rules arrived one entry point at a time and a command that spelled the sequence out again could
leave one behind.
"""

from __future__ import annotations

from collections.abc import Mapping, Set
from dataclasses import dataclass

from keelline.config.schema import Config
from keelline.errors import Refusal
from keelline.project.templates import (
    CI_ARTIFACT,
    CONFIG_ARTIFACT,
    IGNORE_ARTIFACT,
    SHARED_FILE,
    Prepared,
    project_templates,
    retired_stub,
)
from keelline.release.api import Resolution
from keelline.scaffold import Kind, Record, Template

# Fixed text with a count: the ids `[artifacts] local` lists are repository-authored, and which
# of them matched is not printed, only how many.
LOCAL_PROFILE = (
    "[artifacts] local names {count} of the profile's artifacts, and the AGENTS.md pointer and "
    "each harness's rule read them at the path the project commits; take them out of the list"
)


def refuse_local_profile(prepared: Prepared, config: Config) -> None:
    """Refuse a footprint whose profile artifacts `[artifacts] local` would move out of git.

    The engine would write them under `.keelline/local/artifacts/`, while every reader of them
    names `rules_file`'s committed path, so each pointer would lead nowhere. `prepare` asks it for
    `init` and `upgrade`; not for `uninstall`, so a configuration written before the rule can
    still be taken back.
    """
    local = prepared.profiled & set(config.artifacts.local)
    if local:
        raise Refusal(LOCAL_PROFILE.format(count=len(local)))


# The artifacts that do their work only at the repository root: every command reads
# `keelline.toml` there, and the ignore block there is what keeps `.keelline/local/` out of git.
# A copy under `.keelline/local/artifacts/` is never read, and `uninstall` could not remove either
# one before it checks what is left under `.keelline/local/`, because both go after that check.
ROOT_ONLY = (CONFIG_ARTIFACT, IGNORE_ARTIFACT)
# Fixed text: the names interpolated are drawn from `ROOT_ONLY`, artifact ids this build produces,
# never from the repository-authored list.
# `can work` and `take {names} out` rather than `work` and `take them out`: one sentence that
# is grammatical for one id and for two.
LOCAL_ROOT_ONLY = (
    "[artifacts] local names {names}, which can work only at the repository root: every command "
    "reads keelline.toml there, and the ignore block there is what keeps .keelline/local/ out of "
    "git; take {names} out of [artifacts] local"
)


def refuse_local_root_only(config: Config) -> None:
    """Refuse an `[artifacts] local` list naming an artifact that only works at the root.

    `prepare` asks it for `init`, `upgrade` and `uninstall` alike, before any of them plans, so
    none of them writes or removes anything under a configuration that would keep `keelline.toml`
    or the ignore block out of git. For `uninstall` that is the difference between a refusal
    before any write and one part-way, since both are removed after the check of what is left
    under `.keelline/local/`.
    """
    named = [artifact_id for artifact_id in ROOT_ONLY if artifact_id in config.artifacts.local]
    if named:
        raise Refusal(LOCAL_ROOT_ONLY.format(names=" and ".join(named)))


# The kinds that live inside a file somebody else owns.
IN_FILE = frozenset({Kind.MANAGED_REGION, Kind.KEYED_ENTRIES})


def retired_templates(
    could_write: Mapping[str, frozenset[str]], records: Mapping[str, Record], produced: Set[str]
) -> tuple[tuple[Template, ...], int]:
    """The recorded artifacts this configuration no longer produces, and how many are orphans.

    `records` is the committed manifest's. A record is retired only when its target is one
    `could_write` lists for its id: which ids exist, and which targets each could have, are this
    build's. Any other record is an orphan, counted and never touched; its id is
    repository-authored, so only the count is ever printed.

    The engine judges a retired whole file by its record (`templates.retired_stub`). **A region
    leaves as a region**, so a record whose kind says it lived inside a host file is never
    retired this way: the stub names no region, and forced, it would delete the host file and
    everything a person wrote in it. Such a record is an orphan too. A region comes out only
    through the template this build produces for it, which carries its name and comment style.
    The kind is committed, and all it can do here is turn a removal into an orphan.

    Whether to retire a listed one is `prepare`'s policy: `uninstall` retires every one, and
    `upgrade` keeps the workflow unless `[ci] mode` asks for no gate. Both apply the rules above
    through this one function.
    """
    retired = tuple(
        retired_stub(artifact_id, records[artifact_id].target)
        for artifact_id in sorted(records)
        if artifact_id not in produced
        and records[artifact_id].kind not in IN_FILE
        # Exact: a record at a case variant of a place is an orphan, never touched, which only
        # ever keeps a file.
        and records[artifact_id].target in could_write.get(artifact_id, frozenset())
    )
    orphans = sum(1 for artifact_id in records if artifact_id not in produced) - len(retired)
    return retired, orphans


def withheld(could_write: Mapping[str, Set[str]]) -> dict[str, frozenset[str]]:
    """For each artifact id, every target another artifact is built to write, whose place kept
    out of git no ledger entry under that id may name (`scaffold.left_copies`).

    `SHARED_FILE` is the one exception, and it is how the build is made: the `AGENTS.md`
    skeleton and its region share a file by design, so neither withholds the other's place. A
    place two other ids share because committed `[paths]` values coincide is never an exception:
    `project_templates` refuses that configuration, and were it planned, the place would be
    withheld from both.
    """
    return {
        artifact_id: frozenset(
            place
            for other, places in could_write.items()
            if other != artifact_id and not {artifact_id, other} <= SHARED_FILE
            for place in places
        )
        for artifact_id in could_write
    }


@dataclass(frozen=True)
class Passes:
    """What a command plans from: `prepared.once` is the write-once pass, `footprint` the
    footprint pass, retirements included, `orphans` the records neither touches, and `withheld`
    what each id's ledger entries may never name, for every plan of either pass."""

    prepared: Prepared
    footprint: tuple[Template, ...]
    orphans: int
    withheld: Mapping[str, frozenset[str]]


def prepare(
    config: Config,
    records: Mapping[str, Record],
    *,
    resolution: Resolution,
    document: str,
    adopted: bool,
    removing: bool = False,
) -> Passes:
    """The two passes a command plans under `config`, against the manifest's `records`.

    **The refusals, in this order, before anything is planned.** `project_templates`' own (a
    profile this build does not ship, two artifacts of one pass at one file); a profile artifact
    `[artifacts] local` would keep out of git (`refuse_local_profile`), except when `removing`;
    and `keelline.toml` or the ignore block listed there (`refuse_local_root_only`).

    **Retirement.** Every record `retired_templates` lists is retired when `removing`. Otherwise
    the workflow is retired only when `[ci] mode` is `"none"`: a mode this build merely does not
    render is not a request to delete the gate, so its record is kept, neither retired nor an
    orphan.

    **The workflow last**, retirements included. The engine writes a plan in order, and the
    workflow's pin is one value with `[ci] ref`, which `upgrade` writes after the whole footprint;
    planned last, a write that fails part-way leaves the workflow on the ref `keelline.toml` still
    records. The sort is stable, so every other template keeps the order it was built in.
    """
    prepared = project_templates(config, resolution=resolution, document=document, adopted=adopted)
    if not removing:
        refuse_local_profile(prepared, config)
    refuse_local_root_only(config)
    produced = {t.id for t in (*prepared.once, *prepared.footprint)}
    retired, orphans = retired_templates(prepared.could_write, records, produced)
    if not removing:
        retired = tuple(t for t in retired if t.id != CI_ARTIFACT or config.ci.mode == "none")
    footprint = sorted((*prepared.footprint, *retired), key=lambda t: t.id == CI_ARTIFACT)
    return Passes(prepared, tuple(footprint), orphans, withheld(prepared.could_write))
