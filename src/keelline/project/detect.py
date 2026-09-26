"""What `init --yes` can read off a repository without asking, and where each value came from.

Four values, each one `git` question or a probe of the root: the name, the base branch, the
harnesses whose directories the root carries, and the shipped profile whose markers it
carries. `origin_remote` is the memory area's, so "what is this checkout's origin" is asked one
way.

**Three of them are repository-authored strings, and each is held to a grammar before it is
returned:** the remote's last path segment and the checkout's directory name to `[project]
name`'s, and `origin/HEAD`'s branch — or, where no clone recorded one, the branch checked out —
to the one a rendered workflow accepts. A name outside its grammar is refused naming the grammar
and never the value, or, leniently, returned as `""` and `not derivable`, so `init --questions`
asks for it rather than suggesting it. A branch outside its grammar is reported as the default.
The agents and the profile are names from Keelline's own registries.

Each value also says where it came from, in one of this module's fixed phrases, because a
default is only as good as its source: `origin/HEAD` is set by `git clone` and goes stale after
the remote's default branch is renamed, since git does not refresh it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from keelline.config.schema import BRANCH_NAME, NAME_RULE, PROJECT_NAME
from keelline.errors import Refusal
from keelline.gitenv import git_run
from keelline.memory.api import GitUnavailable, origin_remote

DEFAULT_BRANCH = "main"
ORIGIN_PREFIX = "refs/remotes/origin/"
HEADS_PREFIX = "refs/heads/"
NOT_A_NAME = (
    f"the project name this repository suggests is not {NAME_RULE}, so `init` cannot choose "
    "one; answer it with `keelline init --yes "
    "--name NAME`, or write `[project] name` into keelline.toml by hand and run `keelline init "
    "--yes` again, which keeps what you wrote"
)
# Where a value came from: the only words `Detected.sources` holds.
DEFAULT = "default"
NOT_DERIVABLE = "not derivable"
ORIGIN_REMOTE = "origin remote"
DIRECTORY_NAME = "directory name"
ORIGIN_HEAD = "origin/HEAD"
CURRENT_BRANCH = "current branch"
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
    # `origin/HEAD` named a branch outside the grammar, so the base branch is the default in its
    # place. A flag and never the name: the name is the text the grammar refused.
    head_refused: bool = False


def _name(root: Path) -> tuple[str, str]:
    try:
        origin = origin_remote(root)
    except GitUnavailable:
        origin = None
    if origin:
        segment = origin.rstrip("/").replace(":", "/").rsplit("/", 1)[-1]
        # Lower-cased first, so `Widget.GIT` loses its suffix as `Widget.git` does.
        return segment.lower().removesuffix(".git"), ORIGIN_REMOTE
    return root.name.lower(), DIRECTORY_NAME


def _symbolic(root: Path, ref: str, prefix: str) -> str | None:
    """The branch the symbolic `ref` names below `prefix`, unchecked; `""` when it names a ref
    outside `prefix`, and `None` when git records no such symbolic ref.

    The full ref and never `--short`: git shortens a ref only as far as it stays unambiguous, so
    a tag or a local branch named `origin/develop` made `origin/HEAD` read back as
    `remotes/origin/develop`, which passed the grammar and was written as the base branch. The
    clone carries the tag, so that was repository-authored input choosing the configuration.
    """
    code, out = git_run(root, "symbolic-ref", ref)
    if code != 0:
        return None
    full = out.removesuffix("\n")
    return full.removeprefix(prefix) if full.startswith(prefix) else ""


def _base_branch(root: Path) -> tuple[str, str, bool]:
    """The base branch, where it came from, and whether `origin/HEAD` named one outside the
    grammar, so the default stands in its place.

    With no `origin/HEAD` at all — a repository nobody has cloned — the branch checked out is the
    next answer, held to the same grammar: a fresh repository on `develop` had `main` written as
    its base, and a workflow that never ran for a pull request into `develop`. A detached or
    unreadable `HEAD`, or a branch outside the grammar, leaves the default.
    """
    head = _symbolic(root, "refs/remotes/origin/HEAD", ORIGIN_PREFIX)
    if head is not None:
        if BRANCH_NAME.match(head):
            return head, ORIGIN_HEAD, False
        return DEFAULT_BRANCH, DEFAULT, True
    current = _symbolic(root, "HEAD", HEADS_PREFIX)
    if current and BRANCH_NAME.match(current):
        return current, CURRENT_BRANCH, False
    return DEFAULT_BRANCH, DEFAULT, False


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
    base_branch, branch_source, head_refused = _base_branch(root)
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
        head_refused=head_refused,
    )
