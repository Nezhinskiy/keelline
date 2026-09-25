"""What `init --yes` can read off a repository without asking, and where each value came from.

Four values, each one `git` question or a probe of the root: the name, the base branch, the
harnesses whose directories the root carries, and the shipped profile whose markers it
carries. `origin_remote` is the memory area's, so "what is this checkout's origin" is asked one
way.

**Three of them are repository-authored strings, and each is held to a grammar before it is
returned:** the remote's last path segment and the checkout's directory name to `[project]
name`'s, and `origin/HEAD`'s branch to the one a rendered workflow accepts. A name outside its
grammar is refused naming the grammar and never the value, or, leniently, returned as `""` and
`not derivable`, so `init --questions` asks for it rather than suggesting it. A branch outside
its grammar is reported as the default. The agents and the profile are names from Keelline's
own registries.

Each value also says where it came from, in one of this module's fixed phrases, because a
default is only as good as its source: `origin/HEAD` is set by `git clone` and goes stale after
the remote's default branch is renamed, since git does not refresh it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from keelline.config.schema import PROJECT_NAME
from keelline.errors import Refusal
from keelline.gitenv import git_run
from keelline.memory.api import GitUnavailable, origin_remote
from keelline.project.templates import GATE_BRANCH

DEFAULT_BRANCH = "main"
NOT_A_NAME = (
    "the project name this repository suggests is not one lowercase path segment matching "
    f"{PROJECT_NAME.pattern}, so `init` cannot choose one; write `[project] name` into "
    "keelline.toml by hand and run `keelline init --yes` again — it keeps what you wrote"
)
# Where a value came from: the only words `Detected.sources` holds.
DEFAULT = "default"
NOT_DERIVABLE = "not derivable"
ORIGIN_REMOTE = "origin remote"
DIRECTORY_NAME = "directory name"
ORIGIN_HEAD = "origin/HEAD"
HARNESS_DIRECTORIES = "harness directories"
PROFILE_MARKERS = "profile markers"
NO_PROFILE_MARKERS = "no profile markers"


@dataclass(frozen=True)
class Detected:
    name: str
    base_branch: str
    agents: tuple[str, ...]
    # The first shipped profile the root carries markers for, or none.
    profile: str = ""
    # Keyed "name", "base_branch", "agents", "profile"; each value one of this module's phrases.
    sources: Mapping[str, str] = field(default_factory=dict)


def _name(root: Path) -> tuple[str, str]:
    try:
        origin = origin_remote(root)
    except GitUnavailable:
        origin = None
    if origin:
        segment = origin.rstrip("/").replace(":", "/").rsplit("/", 1)[-1]
        return segment.removesuffix(".git").lower(), ORIGIN_REMOTE
    return root.name.lower(), DIRECTORY_NAME


def _base_branch(root: Path) -> tuple[str, str]:
    code, out = git_run(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    branch = out.strip().removeprefix("origin/") if code == 0 else ""
    if not GATE_BRANCH.match(branch):
        return DEFAULT_BRANCH, DEFAULT
    return branch, ORIGIN_HEAD


def _agents(root: Path) -> tuple[tuple[str, ...], str]:
    from keelline.harnesses import HARNESSES

    agents = tuple(h.name for h in HARNESSES if (root / h.marker_dir).is_dir())
    if agents:
        return agents, HARNESS_DIRECTORIES
    return tuple(h.name for h in HARNESSES), DEFAULT


def _profile(root: Path) -> tuple[str, str]:
    from keelline.profiles import detects, load_profile, shipped

    profile = next((name for name in shipped() if detects(load_profile(name), root)), "")
    return profile, PROFILE_MARKERS if profile else NO_PROFILE_MARKERS


def detect(root: Path, *, lenient: bool = False) -> Detected:
    """The name, the base branch, the harnesses and the profile, each with its source.

    The refusal is the whole of what this does with a name outside the grammar: the remote's
    last path segment and the checkout's directory name both arrive from outside, so one that is
    not a `PROJECT_NAME` is answered with the grammar and the remedy and with none of its own
    bytes. The loader refuses the same grammar the same way, so writing the name by hand and
    running `init` again is a remedy that reaches the end. `lenient` returns it as `""`, `not
    derivable`, instead, for a caller that asks rather than writes.
    """
    name, name_source = _name(root)
    if not PROJECT_NAME.match(name) and not lenient:
        raise Refusal(NOT_A_NAME)
    if not PROJECT_NAME.match(name):
        name, name_source = "", NOT_DERIVABLE
    base_branch, branch_source = _base_branch(root)
    agents, agents_source = _agents(root)
    profile, profile_source = _profile(root)
    return Detected(
        name,
        base_branch,
        agents,
        profile,
        {
            "name": name_source,
            "base_branch": branch_source,
            "agents": agents_source,
            "profile": profile_source,
        },
    )
