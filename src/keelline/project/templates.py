"""The project footprint as `Template`s (§5.6, §7.2), built from a configuration.

Under the module root beside `templates/overlay/` and resolved by `keelline.templates.tree`
(DC9). The three write-once files are `Kind.ONCE` artifacts in a pass of their own (DC3);
everything else is the footprint pass. Every target is a `config.paths` value, which the
loader has bounded to `PATH_VALUE` (P10) and contained; what this module adds is a file name
under it. A value that reaches a rendered file (`gate_branch` into YAML) is quoted there and
held to `GATE_BRANCH` besides, and a value outside it costs the artifact rather than the run.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import keelline
from keelline.attach.api import IGNORE_BODY, IGNORE_REGION
from keelline.config.schema import Config
from keelline.docs.api import trail_path
from keelline.errors import Failure
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
# Named and never quoted: the value is repository-authored, so the refusal names the key and
# the grammar and leaves the bytes where they were (DC6).
BAD_BRANCH = "[ci] gate_branch is not a plain branch name, so no workflow was rendered around it"


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
    """The rendered workflow, or the one sentence saying why this configuration gets none."""
    if config.ci.mode == "none":
        return None, NO_CI
    if config.ci.mode == "uvx":
        return None, UVX_LATER
    if not resolution.asked:
        return None, NOT_ASKED
    if resolution.pin is None:
        return None, NO_TAG
    if not GATE_BRANCH.match(config.ci.gate_branch):
        return None, BAD_BRANCH
    pin, gate, version = resolution.pin, config.ci.gate_branch, keelline.__version__
    return (
        _template(
            "ci-workflow",
            CI_WORKFLOW,
            "keelline.yml",
            render=lambda: fill(
                read("keelline.yml"),
                SLUG=keelline.REPOSITORY_SLUG,
                SHA=pin.sha,
                VERSION=version,
                GATE_BRANCH=gate,
            ),
        ),
        None,
    )


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
    return Prepared(once, tuple(footprint), skipped)
