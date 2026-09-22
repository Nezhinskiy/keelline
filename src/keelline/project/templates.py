"""The project footprint as `Template`s (§5.6, §7.2), built from a configuration.

Under the module root beside `templates/overlay/` and resolved by `keelline.templates.tree`
(DC9). The three write-once files are `Kind.ONCE` artifacts in a pass of their own (DC3);
everything else is the footprint pass. Every target is a `config.paths` value, which the
loader has bounded to `PATH_VALUE` (P10) and contained; what this module adds is a file name
under it. A value that reaches a rendered file (`gate_branch` and `ref` into YAML) is quoted or
shape-checked there — `GATE_BRANCH`, `CI_REF` — and a value outside its grammar costs the
artifact rather than the run.

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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import keelline
from keelline.attach.api import IGNORE_BODY, IGNORE_REGION
from keelline.config.schema import Config
from keelline.docs.api import trail_path
from keelline.errors import Failure, Refusal
from keelline.ledger.api import render_index
from keelline.project.layout import PROJECT_FILES
from keelline.release.api import Resolution
from keelline.scaffold import Kind, Style, Template
from keelline.templates import tree

PROJECT = "project"
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
NOT_ASKED = (
    "the public repository could not be asked for its tags, so there is no commit to pin; "
    "run `keelline init --yes` again with the network reachable, or wait for "
    "`keelline upgrade` (ships later)"
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
NO_REF = (
    "the keelline.toml this repository already had records no [ci] ref, and `init` does not "
    "write into a document it did not create — so a workflow would pin a ref nothing records; "
    "write a released commit into [ci] ref by hand and run `keelline init --yes` again, or wait "
    "for `keelline upgrade` (ships later)"
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
# a `KeyError` at the moment somebody's configuration collides.
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
    once: tuple[Template, ...]
    footprint: tuple[Template, ...]
    skipped: dict[str, str]


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
    pinned to the literal `%%SHA%%`, or an instruction file headed `%%NAME%%`. Refusing costs
    the artifact; writing it costs the project's CI.
    """
    for key, value in values.items():
        text = text.replace(f"%%{key}%%", value)
    left = _SENTINEL.search(text)
    if left is not None:
        raise Failure(f"a template sentinel was left unfilled: {left.group(0)}")
    return text


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
    return Template(
        id=artifact_id,
        kind=kind,
        target=target,
        source=f"{PROJECT}/{name}",
        render=render or partial(read, name),
        region=region,
        style=style,
    )


def _ci(config: Config, resolution: Resolution) -> tuple[Template | None, str | None]:
    """The rendered workflow, or the one sentence saying why this configuration gets none.

    The ref rendered is `config.ci.ref` and never `resolution.pin` — see the module docstring's
    invariant. `resolution` is still read, but only to say *why* there is no ref to render when
    there is none: "the remote could not be asked" and "no released tag matches" are different
    findings from "the document this repository already had records none", and a run that
    collapsed them would send an operator to the network for a file they have to edit.
    """
    if config.ci.mode == "none":
        return None, NO_CI
    if config.ci.mode == "uvx":
        return None, UVX_LATER
    ref = config.ci.ref
    if not ref:
        if not resolution.asked:
            return None, NOT_ASKED
        if resolution.pin is None:
            return None, NO_TAG
        return None, NO_REF
    if not CI_REF.match(ref):
        return None, BAD_REF
    if not GATE_BRANCH.match(config.ci.gate_branch):
        return None, BAD_BRANCH
    # The trailing comment names the release when this run is the one that resolved the ref, and
    # says where the ref came from otherwise — a `# v0.1.0` beside a ref the repository recorded
    # would assert that some other release's commit is this one.
    gate = config.ci.gate_branch
    resolved = resolution.pin is not None and resolution.pin.sha == ref
    note = f"# v{keelline.__version__}" if resolved else "# from [ci] ref"
    return (
        _template(
            "ci-workflow",
            CI_WORKFLOW,
            "keelline.yml",
            render=lambda: fill(
                read("keelline.yml"),
                SLUG=keelline.REPOSITORY_SLUG,
                REF=ref,
                PIN_NOTE=note,
                GATE_BRANCH=gate,
            ),
        ),
        None,
    )


def _one_target_each(templates: Sequence[Template]) -> None:
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
                    first_key=PATH_KEYS[first],
                    second=template.id,
                    second_key=PATH_KEYS[template.id],
                )
            )
        seen[template.target] = template.id


def project_templates(
    root: Path, config: Config, *, resolution: Resolution, document: str
) -> Prepared:
    """The footprint this configuration asks for, split into the engine's two passes (DC3).

    `trail_path` contains its answer against `root`, so `relative_to(root)` hands the engine
    the relative target it re-contains rather than an absolute one it would refuse.
    """
    p = config.paths
    once = (
        _template("config", CONFIG_FILE, "config", kind=Kind.ONCE, render=lambda: document),
        _template(
            "agents-skeleton",
            p.agents_md,
            "agents-skeleton.md",
            kind=Kind.ONCE,
            render=lambda: fill(read("agents-skeleton.md"), NAME=config.project.name),
        ),
        _template("claude-md", CLAUDE_MD, "claude.md", kind=Kind.ONCE),
    )
    footprint: list[Template] = [
        _template("documentation-policy", f"{p.architecture}/documentation.md", "documentation.md"),
        _template("adr-template", f"{p.adr}/0000-template.md", "adr-template.md"),
        _template("ledger-runbook", f"{p.runbooks}/bug-reports.md", "bug-reports-runbook.md"),
        _template("ledger-audits", f"{p.bugs}/audits/README.md", "audits-readme.md"),
        _template("bug-index", p.bug_index, "bug-index", render=lambda: render_index([], config)),
        _template("roadmap", p.roadmap, "roadmap.md"),
        _template("roadmap-history", p.roadmap_history, "roadmap-history.md"),
        _template("trail", str(trail_path(root, config).relative_to(root)), "trail.toml"),
        _template("specs-keep", f"{p.specs}/.gitkeep", "gitkeep"),
        _template("plans-keep", f"{p.plans}/.gitkeep", "gitkeep"),
        _template(
            "gitignore",
            ".gitignore",
            "gitignore",
            kind=Kind.MANAGED_REGION,
            render=lambda: IGNORE_BODY,
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
            ),
            region=HARNESS_REGION,
        ),
    ]
    skipped: dict[str, str] = {}
    workflow, reason = _ci(config, resolution)
    if workflow is not None:
        footprint.append(workflow)
    elif reason is not None:
        skipped["ci-workflow"] = reason
    _one_target_each(once)
    _one_target_each(footprint)
    return Prepared(once, tuple(footprint), skipped)
