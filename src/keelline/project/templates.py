"""The project footprint as `Template`s (§5.6, §7.2), built from a configuration.

Under the module root beside `templates/overlay/` and resolved by `keelline.templates.tree`
(DC9). The three write-once files are `Kind.ONCE` artifacts in a pass of their own (DC3);
everything else is the footprint pass. Every target is a `config.paths` value, which the
loader has bounded to `PATH_VALUE` (P10) and contained; what this module adds is a file name
under it. A value that reaches a rendered file (`gate_branch` and `ref` into YAML) is quoted or
shape-checked there — `GATE_BRANCH`, `CI_REF` — and a value outside its grammar costs the
artifact rather than the run.

**Every write-once file this renders answers to the configuration, including the two that look
like fixed text.** `CLAUDE.md` is a one-line pointer and its one line is `[paths] agents_md`: it
was the literal `@AGENTS.md`, so a project that renamed the instruction file got a pointer at a
file that was not there and a `docs check` that passed anyway, and every session in it followed
the dangling pointer. The skeleton's budget sentence is the same shape — it states the numbers
`keelline docs check` enforces, so it is filled from `Budgets.effective` rather than from three
literals copied out of the preset.

**One invariant governs the workflow: its `uses:` ref is always what `[ci] ref` says on disk
after the run.** That is what `doctor`'s `ci-ref` row enforces from the other side — "the
workflow pins a different ref from `[ci] ref`, so the gate that runs is not the one recorded" —
and it is why the workflow is rendered from `config.ci.ref` and never from the resolution
directly. `init` writes a resolved pin into the document only when it is the run that creates
the document, so on the adoption path `config.ci.ref` is the repository's own recorded value and
the workflow pins that; where the adopted document records none, no workflow is written at all.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import keelline
from keelline.attach.api import IGNORE_BODY, IGNORE_REGION
from keelline.config.layout import rules_file
from keelline.config.schema import Config
from keelline.docs.api import trail_path
from keelline.errors import Failure, Refusal
from keelline.ledger.api import render_index
from keelline.project.layout import PROJECT_FILES
from keelline.release.api import Resolution
from keelline.scaffold import Kind, Style, Template, validate_sources
from keelline.templates import tree

if TYPE_CHECKING:
    from keelline.profiles import Profile

PROJECT = "project"
# The provenance namespace for an artifact whose bytes this module *computes*, so that a record
# of one never claims a file the wheel does not carry.
#
# `Template.source` becomes `Record.template` in `.keelline/manifest.json`, which is committed and
# is what `upgrade` will read to find out where an artifact's bytes came from. Three artifacts
# here have no shipped file at all — `config` is the rendered document, `bug-index` is
# `render_index([], config)`, `gitignore` is `IGNORE_BODY` — and all three recorded
# `project/<id>`, a name absent from `PROJECT_FILES` and from the tree, which `read` itself
# refuses. Nothing broke today only because each one overrides `render`; the committed fixture's
# manifest carried `"template": "project/gitignore"`, a pointer at nothing, for as long as it has
# existed.
#
# A separate namespace rather than a name that looks readable: "there is no shipped file, these
# bytes are built" is the honest answer, and a reader — `upgrade`, a person, `doctor` — can tell
# it from `project/roadmap.md` without asking the wheel. It stays one string, so the manifest
# format is untouched. `_computed` is the only place it is spelled, and
# `tests/project/test_templates.py` holds every source both passes build to one rule or the other.
COMPUTED = "computed"
# The provenance namespace for an artifact whose bytes are a shipped profile's file:
# `profile/<name>/rules.md` names a file the wheel carries under `keelline/profiles/`.
PROFILE = "profile"
CLAUDE_MD = "CLAUDE.md"
CONFIG_FILE = "keelline.toml"
HARNESS_REGION = "harness"
CI_WORKFLOW = ".github/workflows/keelline.yml"
# The grammar `[ci] gate_branch` must match before it is written into the rendered workflow.
# The value is repository-authored and lands in two places in one YAML file — a `branches:`
# list and a shell-free `${{ }}` default — so it is quoted there *and* held to a shape here:
# quoting alone would still admit a newline, which closes the list and writes further keys.
GATE_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
# The grammar `[ci] ref` must match before it is written into the rendered workflow's `uses:`
# line, for the same reason `GATE_BRANCH` exists and with the same provenance: the value is
# repository-authored — on the adoption path it is whatever `keelline.toml` already carried —
# and it lands in a YAML file GitHub executes. A full-length sha and nothing else: it is the
# only immutable reference a reusable workflow can take (D16), it is the only form `doctor`'s
# `ci-ref` row can resolve against the public repository's tags, and the documented mutable
# `v1` alias is a file a project writes by hand rather than one `init` renders. The anchor is
# this constant in the installed package; nothing a repository writes can move it.
CI_REF = re.compile(r"\A[0-9a-f]{40}\Z")
_SENTINEL = re.compile(r"%%[A-Z_]+%%")
NO_TAG = (
    "no released Keelline tag matches the version running, so there is no commit to pin; "
    "`keelline upgrade` (ships later) writes it after the first release"
)
# Two remedies, picked by the kind of run, for the reason `NO_REF`'s comment gives: a run that
# writes persists `.keelline/manifest.json`, and `init` refuses a repository that has one, so
# "run again with the network reachable" is a remedy only a dry run can still take. After a run
# that wrote, the document records no ref and nothing `init` does will add one.
NOT_ASKED = "the public repository could not be asked for its tags, so there is no commit to pin; "
NOT_ASKED_DRY = (
    NOT_ASKED + "run `keelline init --yes` with the network reachable, and that run pins it"
)
NOT_ASKED_WRITTEN = NOT_ASKED + (
    "the run that writes keelline.toml is the only one that pins, and `init` does not run twice "
    "on one repository — write a released commit into [ci] ref and the workflow by hand, or "
    "wait for `keelline upgrade` (ships later)"
)
UVX_LATER = (
    'the uvx form of the gate ships with a later lane; [ci] mode = "reusable" is what this '
    "Keelline renders"
)
NO_CI = "[ci] mode is none"
# Both fixed text, and neither carries the value. `NO_REF` is the adoption path's own state: the
# document is a create-once artifact that is already there, so a pin this run resolved would be
# recorded nowhere, and a workflow pinned to it would be the ref `doctor` reports as disagreeing
# with `[ci] ref` on the very next run.
#
# It answers that whole path and not one case of it, so the second sentence says what the first
# one leaves open: the remote's answer is not the reason and asking again is not the remedy.
# Without it the wording reads as "a pin resolved and nothing recorded it", and the two states
# that reach here with no pin — the remote unreachable, no released tag — were reported with
# `NOT_ASKED` and `NO_TAG`, both of which send the operator to the network for a file they have
# to edit by hand.
#
# The remedy names the one run that can still act on it. "Run `keelline init --yes` again" was
# already dead where this sentence prints from a completed run: `apply` persists
# `.keelline/manifest.json`, and `init` refuses a repository that has one ("re-running `init` is
# `keelline upgrade`, which ships later"). Measured on a repository adopted with no `[ci] ref`:
# the second run is a refusal, not a workflow. So the sentence says which run the pin has to be
# in place for, and who writes the file after that.
NO_REF = (
    "the keelline.toml this repository already had records no [ci] ref, and `init` does not "
    "write into a document it did not create — so a workflow would pin a ref nothing records. "
    "That is the whole reason, whatever this run could or could not resolve from the public "
    "repository: write a released commit into [ci] ref by hand, and `keelline init --yes` "
    "renders the workflow around it on a repository it has not initialised yet; on one it "
    "already has, the workflow is yours to write, or wait for `keelline upgrade` (ships later)"
)
BAD_REF = (
    "[ci] ref is not a full-length commit sha, so no workflow was rendered around it; the "
    "mutable `v1` alias is documented and is yours to write by hand"
)
# Named and never quoted: the value is repository-authored, so the refusal names the key and
# the grammar and leaves the bytes where they were (DC6).
BAD_BRANCH = "[ci] gate_branch is not a plain branch name, so no workflow was rendered around it"


# Which `[paths]` key each artifact's target is built from, so the collision refusal below can
# name what to edit. Two statements of one thing, the way `PROJECT_FILES` and the shipped tree
# are: `tests/project/test_templates.py` holds this mapping's key set to the artifact ids both
# passes actually produce, so an artifact added without a line here reddens rather than reaching
# a `KeyError` at the moment somebody's configuration collides. A harness's rendition is not
# listed: its target is the harness's own fixed name, and `project_templates` adds its row where
# it appends the rendition, so a harness added to the registry needs no line here.
OWN_NAME = "a fixed name of Keelline's own"
PATH_KEYS = {
    "config": OWN_NAME,
    "agents-skeleton": "paths.agents_md",
    "claude-md": OWN_NAME,
    "documentation-policy": "paths.architecture",
    "adr-template": "paths.adr",
    "ledger-runbook": "paths.runbooks",
    "ledger-audits": "paths.bugs",
    "bug-index": "paths.bug_index",
    "roadmap": "paths.roadmap",
    "roadmap-history": "paths.roadmap_history",
    "trail": "paths.roadmap",
    "specs-keep": "paths.specs",
    "plans-keep": "paths.plans",
    "gitignore": OWN_NAME,
    "agents-md": "paths.agents_md",
    "ci-workflow": OWN_NAME,
    "profile-rules": "paths.keelline",
}
# Fixed text with two artifact ids and two `[paths]` key names interpolated — all four are
# Keelline's own vocabulary. The colliding path is a repository-authored value and is not printed.
ONE_TARGET = (
    "two artifacts of one pass resolve to the same file: {first} ({first_key}) and {second} "
    "({second_key}). The engine writes a plan in order, so the second would replace the first "
    "with no verb saying so and the manifest would record two different digests for one path — "
    "separate them under [paths] in keelline.toml and run `keelline init --yes` again"
)


@dataclass(frozen=True)
class Prepared:
    """Both passes, the reasons an artifact was not rendered, and every target this build could
    write for each artifact id under any configuration.

    `could_write` is built at the lines that build the templates, from the same calls, so it
    cannot describe a target the footprint could not have: for the conditional artifacts it holds
    the workflow's one path, and each shipped profile's neutral rules and renditions, whichever of
    them this configuration asks for. `upgrade` and `uninstall` retire a recorded artifact this
    configuration no longer produces only at a target listed here for its id.
    """

    once: tuple[Template, ...]
    footprint: tuple[Template, ...]
    skipped: dict[str, str]
    could_write: Mapping[str, frozenset[str]]
    # How many names in `[keelline] agents` no harness answers to; counted, never quoted.
    unknown_harnesses: int = 0
    # The profile's own artifacts in this footprint. Every reader of them, the `AGENTS.md`
    # pointer and each harness's rule, names the committed path.
    profiled: frozenset[str] = frozenset()


# Fixed text with a count: the ids `[artifacts] local` lists are repository-authored, and which
# of them matched is not printed, only how many.
LOCAL_PROFILE = (
    "[artifacts] local names {count} of the profile's artifacts, and the AGENTS.md pointer and "
    "each harness's rule read them at the path the project commits; take them out of the list"
)


def refuse_local_profile(prepared: Prepared, config: Config) -> None:
    """Refuse a footprint whose profile artifacts `[artifacts] local` would move out of git.

    The engine would write them under `.keelline/local/artifacts/`, while every reader of them
    names `rules_file`'s committed path, so each pointer would lead nowhere. `init` and `upgrade`
    call this before they plan; `uninstall` does not, so a configuration written before the rule can
    still be taken back.
    """
    local = prepared.profiled & set(config.artifacts.local)
    if local:
        raise Refusal(LOCAL_PROFILE.format(count=len(local)))


def read(name: str) -> str:
    """One shipped template's text, refusing a name this package does not ship.

    The check is before the join and not after: `name` decides which file under the tree is
    opened, and `PROJECT_FILES` is the plugin's own list — the party being contained here is a
    caller inside this package, and the anchor is a constant in the wheel beside the files it
    names, which nothing a repository writes can move.
    """
    if name not in PROJECT_FILES:
        raise Failure(f"{name} is not a shipped project template")
    root = tree(PROJECT)
    if not root.is_dir():
        raise Failure(f"the project template tree is not readable at {root}")
    return (root / name).read_text(encoding="utf-8")


def fill(text: str, **values: str) -> str:
    """Replace every `%%KEY%%` sentinel, and refuse a template with one left in it.

    A sentinel that survives would be written into a project's file verbatim — a `uses:` line
    pinned to the literal `%%REF%%`, or an instruction file headed `%%NAME%%`. Refusing costs
    the artifact; writing it costs the project's CI.
    """
    for key, value in values.items():
        text = text.replace(f"%%{key}%%", value)
    left = _SENTINEL.search(text)
    if left is not None:
        raise Failure(f"a template sentinel was left unfilled: {left.group(0)}")
    return text


def _budget(config: Config, name: str) -> str:
    """One budget, rendered the way the skeleton's prose reads it.

    The skeleton tells a project the numbers `keelline docs check` will hold it to, and those
    numbers were three literals — the preset's — written into a file `init` renders into somebody
    else's repository. A project that lowers `agents_md_lines` to 250 was handed a document
    Keelline itself wrote saying 300 was fine, and then failed at 251 by the same tool. So the
    numbers come from `Budgets.effective`, which is the preset lowered by any override, and the
    template carries sentinels instead.

    **Grouped, with `,`.** One rule for all three rather than one per number: the prose this
    replaces read "at most 300 lines and 3,000 words ... under 50 lines", so grouping is what it
    already did, and `format(n, ",")` reproduces those three bytes exactly at the preset's
    defaults. A four-digit budget written bare would read as a different kind of number from the
    one the sentence next to it carries.
    """
    return format(config.budgets.effective(name), ",")


def _template(
    artifact_id: str,
    target: str,
    name: str,
    *,
    kind: Kind = Kind.TEMPLATE,
    render: Callable[[], str] | None = None,
    region: str | None = None,
    style: Style = Style.MARKDOWN,
) -> Template:
    """An artifact whose bytes begin as `templates/project/<name>`, shipped in the wheel.

    `name` is a `PROJECT_FILES` entry — `read` refuses anything else — and it is also the
    provenance recorded for the artifact. A `render` override here still reads that file and
    fills its sentinels, so the record's `project/<name>` stays true of it; an artifact with no
    shipped file at all is `_computed`'s and not this one's.
    """
    return Template(
        id=artifact_id,
        kind=kind,
        target=target,
        source=f"{PROJECT}/{name}",
        render=render or partial(read, name),
        region=region,
        style=style,
    )


def _computed(
    artifact_id: str,
    target: str,
    render: Callable[[], str],
    *,
    kind: Kind = Kind.TEMPLATE,
    region: str | None = None,
    style: Style = Style.MARKDOWN,
) -> Template:
    """An artifact this module builds, whose provenance therefore names no shipped file.

    A second constructor rather than a flag or a `None` name on `_template`: which artifacts have
    a file in the wheel is decided here, once per artifact, at the line that builds it — and
    every argument of both functions is then total, with no arm that a caller could reach only by
    passing an impossible pair. `render` is required for the same reason: there is nothing to
    fall back to reading.
    """
    return Template(
        id=artifact_id,
        kind=kind,
        target=target,
        source=f"{COMPUTED}/{artifact_id}",
        render=render,
        region=region,
        style=style,
    )


def _profiled(artifact_id: str, target: str, profile: Profile) -> Template:
    """An artifact whose bytes are a shipped profile's file, so its provenance names that file.

    The third constructor beside `_template` and `_computed`, for the reason those two give for
    being two: which namespace an artifact's bytes come from is decided at the line that builds
    it.
    """
    from keelline.profiles import RULES_FILE

    return Template(
        id=artifact_id,
        kind=Kind.TEMPLATE,
        target=target,
        source=f"{PROFILE}/{profile.name}/{RULES_FILE}",
        render=lambda: profile.rules,
    )


PROFILE_BLOCK = (
    "\n\nThe `{name}` profile's rules are in `{path}`. Before the first command:\n\n{lines}"
)


def _profile_block(profile: Profile | None, rules: str) -> str:
    """The universal adapter: what every harness reading `AGENTS.md` is handed.

    It opens with the blank line that separates it from the region's paragraph and ends without
    a newline, so a project with no profile renders the region byte for byte as before.
    """
    if profile is None:
        return ""
    lines = "\n".join(f"- {line}" for line in profile.essentials)
    return PROFILE_BLOCK.format(name=profile.name, path=rules, lines=lines)


def _ci(
    config: Config, resolution: Resolution, *, adopted: bool, dry_run: bool
) -> tuple[Template | None, str | None]:
    """The rendered workflow, or the one sentence saying why this configuration gets none.

    The ref rendered is `config.ci.ref` and never `resolution.pin` — see the module docstring's
    invariant. `resolution` is still read, but only to say *why* there is no ref to render when
    there is none: "the remote could not be asked" and "no released tag matches" are different
    findings from "the document this repository already had records none", and a run that
    collapsed them would send an operator to the network for a file they have to edit.

    **`adopted` is read before `resolution` is, and that order is the rule above.** This
    function had the inverse of its own docstring: it could not see which kind of run it was in,
    so on a repository with a hand-written `keelline.toml` — the ordinary adoption path, under
    the preset's `[ci] mode = "reusable"` — an unreachable remote was reported as `NOT_ASKED`
    ("run `keelline init --yes` again with the network reachable") and a pre-release Keelline as
    `NO_TAG`. Running again cannot help either one: `keelline.toml` is a `Kind.ONCE` artifact
    already on disk, so no pin this run or any later run resolves is ever recorded, and the
    workflow is skipped again for ever. The remote's answer is not what is missing here, and
    `NO_REF` is the sentence that says what is.
    """
    if config.ci.mode == "none":
        return None, NO_CI
    if config.ci.mode == "uvx":
        return None, UVX_LATER
    ref = config.ci.ref
    if not ref:
        if adopted:
            return None, NO_REF
        if not resolution.asked:
            return None, NOT_ASKED_DRY if dry_run else NOT_ASKED_WRITTEN
        if resolution.pin is None:
            return None, NO_TAG
        return None, NO_REF
    if not CI_REF.match(ref):
        return None, BAD_REF
    if not GATE_BRANCH.match(config.ci.gate_branch):
        return None, BAD_BRANCH
    # Rendered from `config` alone: the same configuration renders the same bytes online,
    # offline and before any release, so an up-to-date workflow never reads as refreshed.
    gate = config.ci.gate_branch
    return (
        _template(
            "ci-workflow",
            CI_WORKFLOW,
            "keelline.yml",
            render=lambda: fill(
                read("keelline.yml"),
                SLUG=keelline.REPOSITORY_SLUG,
                REF=ref,
                GATE_BRANCH=gate,
            ),
        ),
        None,
    )


def retired_templates(
    could_write: Mapping[str, frozenset[str]], recorded: Mapping[str, str], produced: Set[str]
) -> tuple[tuple[Template, ...], int]:
    """The recorded artifacts this configuration no longer produces, and how many are orphans.

    `recorded` is the committed manifest's `{id: target}`. A record is retired only when its
    target is one `could_write` lists for its id: which ids exist, and which targets each could
    have, are this build's. Any other record is an orphan, counted and never touched; its id is
    repository-authored, so only the count is ever printed.

    The engine judges a retired whole file by its record (`_plan_retired` reads the file and the
    record), so `render` is a stub, built by `_computed` like every other template with no
    shipped file.
    Whether to retire a listed one is the caller's policy: `uninstall` retires every one, and
    `upgrade` keeps the workflow unless `[ci] mode` asks for no gate.
    """
    retired = tuple(
        replace(_computed(artifact_id, target, lambda: ""), retired=True)
        for artifact_id, target in sorted(recorded.items())
        if artifact_id not in produced and target in could_write.get(artifact_id, frozenset())
    )
    orphans = sum(1 for artifact_id in recorded if artifact_id not in produced) - len(retired)
    return retired, orphans


def _one_target_each(templates: Sequence[Template], keys: Mapping[str, str] = PATH_KEYS) -> None:
    """Refuse a pass in which two artifacts resolve to one file (DC3).

    DC3's two-pass design rests on "two artifacts cannot target one file in one pass" being
    true, and nothing made it true: `scaffold.engine.plan` has no duplicate-target detection and
    C2 is frozen, so the rule belongs where the targets are built. Measured before this guard,
    with `paths.roadmap` and `paths.roadmap_history` set to one path: both plans reported zero
    refusals, `apply` wrote both, the file held only `roadmap-history`'s bytes, and the manifest
    recorded two different `sha256` values for one target — so the roadmap's trail block was
    silently lost, `upgrade` would read one record as hand-edited for ever, and `uninstall` would
    remove a file holding the other artifact. `paths.agents_md = "CLAUDE.md"` collides the same
    way in the write-once pass.

    **The anchor is this module's own artifact list**, a constant in the installed package: which
    artifacts exist, and which `[paths]` key each one reads, are Keelline's and not a
    repository's. What the repository chooses is the *values*, and the refusal names the two keys
    so that the remedy is one edit — it never names the value, which is its bytes.

    Only within a pass. `agents-skeleton` and `agents-md` deliberately target one file across the
    two, which is the whole reason there are two.
    """
    seen: dict[str, str] = {}
    for template in templates:
        first = seen.get(template.target)
        if first is not None:
            raise Refusal(
                ONE_TARGET.format(
                    first=first,
                    first_key=keys[first],
                    second=template.id,
                    second_key=keys[template.id],
                )
            )
        seen[template.target] = template.id


def project_templates(
    root: Path,
    config: Config,
    *,
    resolution: Resolution,
    document: str,
    adopted: bool,
    dry_run: bool,
) -> Prepared:
    """The footprint this configuration asks for, split into the engine's two passes (DC3).

    `trail_path` contains its answer against `root`, so `relative_to(root)` hands the engine
    the relative target it re-contains rather than an absolute one it would refuse.

    `adopted` says whether this run read a `keelline.toml` it did not write, and it is threaded
    rather than derived: `_ci` cannot tell the two kinds of run apart from a `Config` and a
    `Resolution`, and every sentence it can print about a missing `[ci] ref` is wrong for one of
    them. It has no default, because a caller that forgot one would silently get the wrong half.
    `dry_run` is threaded for the same reason and with the same rule: the one remedy that
    differs between a run that writes and one that does not is "run it again".
    """
    from keelline.harnesses import HARNESSES, select
    from keelline.profiles import load_profile, shipped

    # The engine's rule first: an unshipped or malformed name is refused naming the grammar and
    # the listing, before `load_profile`'s own refusal, which names neither.
    validate_sources(config)
    profile = load_profile(config.keelline.profile) if config.keelline.profile else None
    rules = rules_file(config, profile.name) if profile is not None else ""
    harnesses, unknown_harnesses = select(config.keelline.agents)
    p = config.paths
    once = (
        _computed("config", CONFIG_FILE, lambda: document, kind=Kind.ONCE),
        _template(
            "agents-skeleton",
            p.agents_md,
            "agents-skeleton.md",
            kind=Kind.ONCE,
            render=lambda: fill(
                read("agents-skeleton.md"),
                NAME=config.project.name,
                LINES=_budget(config, "agents_md_lines"),
                WORDS=_budget(config, "agents_md_words"),
                STATUS_LINES=_budget(config, "status_lines"),
            ),
        ),
        _template(
            "claude-md",
            CLAUDE_MD,
            "claude.md",
            kind=Kind.ONCE,
            render=lambda: fill(read("claude.md"), AGENTS_MD=p.agents_md),
        ),
    )
    footprint: list[Template] = [
        _template("documentation-policy", f"{p.architecture}/documentation.md", "documentation.md"),
        _template("adr-template", f"{p.adr}/0000-template.md", "adr-template.md"),
        _template("ledger-runbook", f"{p.runbooks}/bug-reports.md", "bug-reports-runbook.md"),
        _template("ledger-audits", f"{p.bugs}/audits/README.md", "audits-readme.md"),
        _computed("bug-index", p.bug_index, lambda: render_index([], config)),
        _template("roadmap", p.roadmap, "roadmap.md"),
        _template("roadmap-history", p.roadmap_history, "roadmap-history.md"),
        _template("trail", str(trail_path(root, config).relative_to(root)), "trail.toml"),
        _template("specs-keep", f"{p.specs}/.gitkeep", "gitkeep"),
        _template("plans-keep", f"{p.plans}/.gitkeep", "gitkeep"),
        _computed(
            "gitignore",
            ".gitignore",
            lambda: IGNORE_BODY,
            kind=Kind.MANAGED_REGION,
            region=IGNORE_REGION,
            style=Style.HASH,
        ),
        _template(
            "agents-md",
            p.agents_md,
            "agents-region.md",
            kind=Kind.MANAGED_REGION,
            render=lambda: fill(
                read("agents-region.md"),
                BUG_INDEX=p.bug_index,
                BUGS=p.bugs,
                ROADMAP=p.roadmap,
                SPECS=p.specs,
                PLANS=p.plans,
                PROFILE=_profile_block(profile, rules),
            ),
            region=HARNESS_REGION,
        ),
    ]
    skipped: dict[str, str] = {}
    could_write: dict[str, set[str]] = {}
    workflow, reason = _ci(config, resolution, adopted=adopted, dry_run=dry_run)
    # Where `_ci` builds the workflow, whatever `[ci] mode` asks for now.
    could_write["ci-workflow"] = {CI_WORKFLOW}
    if workflow is not None:
        footprint.append(workflow)
    elif reason is not None:
        skipped["ci-workflow"] = reason
    keys = dict(PATH_KEYS)
    profiled: set[str] = set()
    # Every shipped profile's artifacts are built, so `could_write` lists where each could land;
    # only the configured profile's, for the harnesses this project lists, join the footprint.
    for name in shipped():
        candidate = load_profile(name)
        candidate_rules = rules_file(config, name)
        built = [(True, _profiled("profile-rules", candidate_rules, candidate))]
        for harness in HARNESSES:
            if harness.render_profile is not None:
                rendition = harness.render_profile(candidate, candidate_rules)
                template = _computed(rendition.artifact_id, rendition.target, rendition.render)
                built.append((harness in harnesses, template))
        for wanted, template in built:
            could_write.setdefault(template.id, set()).add(template.target)
            if wanted and name == config.keelline.profile:
                footprint.append(template)
                keys.setdefault(template.id, OWN_NAME)
                profiled.add(template.id)
    _one_target_each(once)
    _one_target_each(footprint, keys)
    for template in (*once, *footprint):
        could_write.setdefault(template.id, set()).add(template.target)
    return Prepared(
        once,
        tuple(footprint),
        skipped,
        could_write={artifact_id: frozenset(t) for artifact_id, t in could_write.items()},
        unknown_harnesses=unknown_harnesses,
        profiled=frozenset(profiled),
    )
