"""What `init --yes` can read off a repository without asking (§8.1).

Three values, each one `git` question or one directory probe. The remote URL and the
directory name are repository-authored, so a refusal names the grammar and never the value
(DC6); `origin_remote` is the memory area's, so "what is this checkout's origin" is asked one
way.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from keelline.config.schema import PROJECT_NAME
from keelline.errors import Refusal
from keelline.gitenv import git_run
from keelline.memory.api import GitUnavailable, origin_remote

DEFAULT_BRANCH = "main"
SURFACES = (("claude", ".claude"), ("codex", ".codex"))
NOT_A_NAME = (
    "the project name this repository suggests is not one lowercase path segment matching "
    f"{PROJECT_NAME.pattern}, so `init` cannot choose one; write `[project] name` into "
    "keelline.toml by hand and run `keelline init --yes` again — it keeps what you wrote"
)


@dataclass(frozen=True)
class Detected:
    name: str
    base_branch: str
    agents: tuple[str, ...]


def _name(root: Path) -> str:
    try:
        origin = origin_remote(root)
    except GitUnavailable:
        origin = None
    if origin:
        return origin.rstrip("/").replace(":", "/").rsplit("/", 1)[-1].removesuffix(".git").lower()
    return root.name.lower()


def _base_branch(root: Path) -> str:
    code, out = git_run(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if code != 0 or not out.strip():
        return DEFAULT_BRANCH
    return out.strip().removeprefix("origin/") or DEFAULT_BRANCH


def detect(root: Path) -> Detected:
    """The name, the base branch and the agent surfaces, or a refusal naming neither value.

    The refusal is the whole of what this module does with a repository-authored string: the
    remote's last path segment and the checkout's directory name both arrive from outside, so
    one that is not a `PROJECT_NAME` is answered with the grammar and the remedy and with none
    of its own bytes. The loader refuses the same grammar the same way, so writing the name by
    hand and running `init` again is a remedy that reaches the end.
    """
    name = _name(root)
    if not PROJECT_NAME.match(name):
        raise Refusal(NOT_A_NAME)
    agents = tuple(agent for agent, directory in SURFACES if (root / directory).is_dir())
    return Detected(name, _base_branch(root), agents or tuple(a for a, _ in SURFACES))
