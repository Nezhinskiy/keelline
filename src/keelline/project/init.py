"""`keelline init --yes`: the footprint, written by the engine in two passes (§8.1, §7.2, DC3).

The three write-once files are `Kind.ONCE` artifacts in a pass of their own and the rest of the
footprint is the second, because two artifacts cannot target one file in one pass. Both are
planned before either is applied, so a refusal anywhere leaves nothing written and no
manifest; the dry run reports both plans and writes nothing.

A repository that already holds a `keelline.toml` and no manifest is adopted. One that holds a
manifest is refused: re-running `init` is `keelline upgrade`.

**The workflow and `[ci] ref` are one value.** A resolved pin is written into the document
only when this run is the one that creates it, and `templates._ci` renders the workflow from
`config.ci.ref` — so the `uses:` ref and what `keelline.toml` says on disk cannot come apart.
`doctor`'s `ci-ref` row reports red when they do, which is why this is the invariant rather than
a convenience.

**Adopted means read, not replaced.** `keelline.toml` is a `Kind.ONCE` artifact, and DC3 says
what that kind is: created when absent, never looked inside again. So on a repository that
already carries one the engine reports `skip_modified` — "create-once, and the file is already
there" — and the file comes back byte for byte. What the hand-written document does is decide
the whole run: it is parsed, merged under Keelline's own two keys and the preset's defaults,
and validated by `loads` before a byte is written, and the `Config` that comes out is what
every target below is built from. The tool-owned keys are written only into a file
Keelline itself creates, which is the only file whose header claims them.

**Every value in the document this writes is either Keelline's own or the repository's own
answer read back.** The tool-owned keys are `config.owned.OWNED`; everything else
is copied from a `keelline.toml` a person wrote, or — where there is none — detected under
`PROJECT_NAME`'s grammar, which is the one thing `detect` refuses outside of. `loads` then
validates the whole document before a byte is written, so a bad path or a bad name costs the
run rather than the repository.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

import keelline
from keelline.config.loader import CONFIG_FILE, loads, toml_position
from keelline.errors import Failure, Refusal
from keelline.project.detect import detect
from keelline.project.footprint import prepare
from keelline.project.templates import CI_ARTIFACT
from keelline.release.api import Resolution, resolve_pin
from keelline.runner import Runner
from keelline.scaffold import MANIFEST_PATH, Plan, apply
from keelline.tomlout import dumps

STATE_NEW = "initialised"
USER_OWNED = ("paths", "memory", "budgets", "ledger", "artifacts", "ci", "gates", "commit_messages")
HEAD_KEYS = ("preset", "profile", "agents")
HEADER = (
    "# Written by `keelline init`. Every key you leave out takes the preset's default;\n"
    "# `[keelline] version`, `state` and `enforced`, and `[ci] ref`, are Keelline's to\n"
    "# rewrite in place; every other key is yours.\n\n"
)
# The pair is spelled literally because the intended reader is an agent relaying this sentence,
# and `--dry-run` on its own is refused by this same refusal: "pass --yes, and --dry-run to read
# them first" reads as two alternatives, one of which does not work.
NEEDS_YES = (
    "`keelline init` writes nothing without --yes; `keelline init --questions` prints the "
    "detected defaults and where each came from — pass --yes to accept them, or --yes --dry-run "
    "to read the plan first"
)
ALREADY = (
    f"{MANIFEST_PATH} exists, so this repository is initialised; re-running `init` is "
    "`keelline upgrade`"
)
ANSWER_SHEET = (
    "this repository already has a keelline.toml, which answers the questions `init` would ask; "
    "edit it, then run `keelline init --yes --dry-run` with no answer flag to read the plan"
)
# The table is Keelline's own vocabulary (`keelline`, `project` or one of `USER_OWNED`), and it
# is the only thing this names: the key that failed is exactly the text no grammar has bounded.
UNWRITABLE_KEY = (
    "keelline.toml's [{table}] table holds a key Keelline cannot write back as a bare TOML key, "
    "so nothing was written; rename it to letters, digits, `_` and `-`"
)
VERB_NOTE = (
    "AGENTS.md is absent: the run writes the skeleton first and the `agents-md` region is then "
    "a region_update into it; a dry run plans it as a create of a region-only file. The bytes "
    "inside the markers are the same either way"
)


@dataclass(frozen=True)
class InitReport:
    once: Plan
    footprint: Plan
    skipped: dict[str, str]
    resolution: Resolution
    adopted: bool
    dry_run: bool
    note: str = ""
    # What `[ci] ref` says on disk after the run, which is what the rendered workflow pins;
    # empty when no workflow was planned. One field for both, because they are one value.
    ref: str = ""
    # How many names in `[keelline] agents` no harness answers to; a count, never the names.
    unknown_harnesses: int = 0

    @property
    def refused(self) -> bool:
        """Whether either plan refused an artifact: the other way than a raised `Refusal` that
        this command refuses, with nothing written."""
        return bool(self.once.refusals or self.footprint.refusals)


def _existing(root: Path) -> dict[str, object] | None:
    """The `keelline.toml` already in the repository, parsed, or `None`.

    A file that will not parse is a `Failure` naming the file and the position `tomllib`
    stopped at, and nothing else the parser had to say. `tomllib`'s own message embeds the
    source for several of its faults — a duplicate table or inline-table key is reported with
    the key in it, and a TOML key is arbitrary quoted text — so the exception is bounded by
    `config.loader.toml_position` before any of it prints. The file is `keelline.toml`, which
    P4 makes an adopted repository's own document, and this refusal is one the `init` skill is
    instructed to relay and stop on.
    """
    path = root / CONFIG_FILE
    if not path.is_file():
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise Failure(f"{CONFIG_FILE} is not valid TOML {toml_position(exc)}") from None


def _tables(
    root: Path, existing: dict[str, object] | None, *, ci: bool
) -> dict[str, dict[str, object]]:
    """The document's tables, in order: Keelline's two keys, then the repository's answers (P4).

    **Detection runs only when no `[project]` table answers for the repository**, and not
    merely when some key of the head is absent. `detect` is the one call here that can refuse
    — a directory name or a remote's last segment outside `PROJECT_NAME` — and DC6's remedy for
    that refusal is to write `[project] name` into `keelline.toml` by hand and run `init`
    again. A branch that consulted `detect` for anything the preset can default would make that
    remedy dead: the repository whose name cannot be guessed would go on being refused after
    doing exactly what it was told. Everything else the head does not carry — `preset`,
    `profile`, `agents` — has a preset default, and the loader supplies it.
    """
    head: dict[str, object] = {"version": keelline.__version__, "state": STATE_NEW}
    tables: dict[str, dict[str, object]] = {"keelline": head}
    old_head = existing.get("keelline") if existing else None
    if isinstance(old_head, dict):
        head.update({k: old_head[k] for k in HEAD_KEYS if k in old_head})
    if existing:
        for name in ("project", *USER_OWNED):
            table = existing.get(name)
            if isinstance(table, dict):
                tables[name] = dict(table)
    if "project" not in tables:
        found = detect(root)
        head.setdefault("agents", list(found.agents))
        if found.profile:
            head.setdefault("profile", found.profile)
        tables["project"] = {
            "name": found.name,
            "base_branch": found.base_branch,
            "release_branch": found.base_branch,
        }
    if not ci:
        tables.setdefault("ci", {})["mode"] = "none"
    return tables


def _rendered(tables: dict[str, dict[str, object]]) -> str:
    """The document `loads` validates: `HEADER` and `tables`, rendered by `tomlout.dumps`.

    Every table but Keelline's own head is copied out of a hand-written document, and `dumps`
    refuses a key it cannot write bare by quoting it (`{name!r}`). A TOML key is arbitrary quoted
    text, so that put repository bytes, ESC and all, into a refusal the `init` skill relays to a
    model, ahead of the loader's own count-only answer. Each table is therefore rendered alone
    first, and a refusal is re-raised naming the table and nothing the document wrote. Rendering
    a table raises only for a key: every value `tomllib` can parse, `dumps` can emit.
    """
    for name, table in tables.items():
        try:
            dumps({name: table})
        except Refusal:
            raise Refusal(UNWRITABLE_KEY.format(table=name)) from None
    return HEADER + dumps(tables)


def precheck(root: Path, *, answering: bool) -> None:
    """The refusals `init` and `init --questions` share, before anything beyond the root is read.

    A manifest means `init` has already run, so re-running it is `keelline upgrade`. While
    `answering` — the questions always are — a `keelline.toml` already answers every question,
    so asking them over it would collect answers that nothing writes.
    """
    if (root / MANIFEST_PATH).is_file():
        raise Refusal(ALREADY)
    if answering and (root / CONFIG_FILE).is_file():
        raise Refusal(ANSWER_SHEET)


def init(
    root: Path, *, machine: Path | None, runner: Runner, yes: bool, dry_run: bool, ci: bool
) -> InitReport:
    """Plan both passes, then apply both — or neither.

    The refusals come in one order and all of them above every write: no `--yes`, a manifest
    that says this repository is already initialised, a `keelline.toml` that is not TOML, a
    detected name outside the grammar, an adopted table holding a key that cannot be written
    back bare (`_rendered`), a `Config` the loader refuses, an artifact at a file another is
    built to write, in either pass (`templates.Owners`), a profile artifact `[artifacts] local`
    would keep out of git (`footprint.refuse_local_profile`), `keelline.toml` or the ignore block
    listed there (`footprint.refuse_local_root_only`), a planned write git ignores
    (`ignored.refuse_ignored`), and finally a refusal in either plan, which is returned rather
    than raised so the report can name the artifact.
    """
    if not yes:
        raise Refusal(NEEDS_YES)
    precheck(root, answering=False)
    existing = _existing(root)
    tables = _tables(root, existing, ci=ci)
    document = _rendered(tables)
    config = loads(document, root, machine=machine)
    # Not asked on the adoption path with no `[ci] ref` either: `_ci` answers that path with
    # `NO_REF` before it reads the resolution, and the ask is a network round trip that can take
    # the whole of its timeout for an answer nothing prints.
    resolution = (
        resolve_pin(keelline.__version__, runner, cwd=root)
        if config.ci.mode == "reusable" and (existing is None or config.ci.ref)
        else Resolution(None, True)
    )
    # `existing is None` and not just "a pin resolved": on the adoption path `config` is a
    # create-once artifact that is already on disk, so nothing written into `tables` here ever
    # reaches a file. Recording the pin anyway made `config.ci.ref` — which is what `_ci`
    # renders the workflow from — disagree with `keelline.toml`, and the workflow was written
    # pinned to a sha the document did not carry. `doctor`'s `ci-ref` row reports exactly that
    # as red, so `init` said it had worked and the next `doctor` said it had not.
    if resolution.pin is not None and existing is None:
        tables.setdefault("ci", {})["ref"] = resolution.pin.sha
        document = _rendered(tables)
        config = loads(document, root, machine=machine)
    # No manifest yet, so nothing to retire: `prepare` for its refusals and the pass order.
    passes = prepare(
        root, config, {}, resolution=resolution, document=document, adopted=existing is not None
    )
    # What `[ci] ref` says on disk after this run, and so what the workflow pins — empty exactly
    # when no workflow was planned. The two are one value by construction, which is the
    # invariant `templates._ci` states and `doctor`'s `ci-ref` row enforces.
    ref = "" if CI_ARTIFACT in passes.skipped else config.ci.ref
    note = VERB_NOTE if not (root / config.paths.agents_md).exists() else ""
    once, footprint = passes.predict((passes.once, ()), (passes.footprint, ()))
    report = InitReport(
        once,
        footprint,
        passes.skipped,
        resolution,
        existing is not None,
        dry_run,
        note,
        ref,
        passes.unknown_harnesses,
    )
    if dry_run or report.refused:
        return report
    apply(root, once)
    # Re-planned against the tree the write-once files are now in: on a repository with no
    # `AGENTS.md`, the region the dry run planned as a create of a region-only file is a
    # `region_update` into the skeleton this pass has just written. `VERB_NOTE` is the sentence
    # that says the bytes inside the markers are the same either way.
    footprint = passes.replan(passes.footprint)
    apply(root, footprint)
    return replace(report, footprint=footprint)
