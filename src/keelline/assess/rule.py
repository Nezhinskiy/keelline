"""The base a change is judged against, and where in it the base's `keelline.toml` is.

A pull request may tighten what its base branch enforces and may not loosen it, so the base's
configuration is the one that governs the run and the change's own is judged against it. Both
halves of that depend on reading the right document, and each way of reading the wrong one ends
in the same place: a base with no `keelline.toml` at the project's path is the bootstrap, where
the change decides its own configuration. So nothing here reads "git did not answer" as "no
copy", and every name and path git would resolve on the caller's behalf is pinned first.

**Which commit.** In CI it is a full commit id the workflow resolved once from the remote-tracking
ref of the base branch, whose name comes from the platform or from the caller workflow's literal
input, which code owners guard (`docs/cli.md#the-reusable-workflow` names the repository
settings). Locally it is `local_base`, the remote-tracking ref of `[project] base_branch`, and
advice only: a local run judges nothing anyone else relies on. Either way `--base` is a full
commit id or a full `refs/…` name, never a short one, because git resolves a short name through
the tags first and a tag of the same spelling would stand in for the branch.

**Where in it.** At the project root's path inside the repository, as git spells it. A root
reached through a symlink below the repository's top, or spelled otherwise than git spells it (a
case-folding disk), is refused rather than guessed at: the base's copy would be looked for at the
place the link or the spelling names, which a change can make empty. A link above the
repository is the machine's (`/tmp` on macOS, a symlinked home) and is admitted.
"""

from __future__ import annotations

import re
from pathlib import Path

from keelline.config.loader import CONFIG_FILE
from keelline.config.schema import Config
from keelline.errors import Failure, Refusal
from keelline.gitenv import NO_ANSWER, git_run, in_work_tree

BASE_UNREADABLE = (
    "the base is not in this checkout, or git could not read its keelline.toml, so the "
    "configuration that governs this change cannot be read; check out with full history "
    "(fetch-depth: 0), or pass a --base that exists"
)
BASE_SHAPE = (
    "--base takes a full 40-character commit id or a full ref name starting with refs/: a "
    "shorter name is resolved by git, and a tag of the same spelling wins"
)
NOT_A_REPOSITORY = (
    "the project root is not inside a git repository, so it has no base to compare with"
)
ROOT_UNANSWERED = (
    "git gave no answer about the repository the project root is in, so its base cannot be "
    f"read: {NO_ANSWER}, or git refused the repository (a checkout of dubious ownership, a "
    "worktree whose git directory is gone)"
)
ROOT_THROUGH_SYMLINK = (
    "the project root is reached through a symlink, or git spells its path differently from the "
    "caller, so the base's keelline.toml would be looked for in the wrong place; pass the root by "
    "its real path"
)
BASE_REF = re.compile(r"\A(?:[0-9a-f]{40}|refs/[A-Za-z0-9._/-]+)\Z")


def local_base(config: Config) -> str:
    """The base a local run is judged against: the remote-tracking ref of the base branch, named
    in full, so no tag can stand in for it while it exists."""
    return f"refs/remotes/origin/{config.project.base_branch}"


def _read(root: Path, *args: str) -> str:
    """git's answer, or the run fails: "git did not answer" is never read as "no copy"."""
    code, out = git_run(root, *args)
    if code != 0:
        raise Failure(BASE_UNREADABLE)
    return out


def repository_prefix(root: Path) -> str:
    """The project root's path inside its repository, `""` at the top or `"a/b/"` below it: git's
    spelling, which is refused unless it is also the caller's."""
    lexical = root.absolute()
    code, out = git_run(lexical, "rev-parse", "--show-toplevel", "--show-prefix")
    if code != 0:
        # Read off the disk, as git finds a repository: git refuses a checkout of dubious
        # ownership exactly as it refuses a directory outside any repository.
        raise Failure(ROOT_UNANSWERED if in_work_tree(lexical) else NOT_A_REPOSITORY)
    top, _, prefix = out.partition("\n")
    # The HIGHEST ancestor that resolves to the top, not the nearest: a component linked back
    # to the top (`app -> .`) resolves to the top as well, and a spelling read below it skips it.
    chain = (*reversed(lexical.parents), lexical)
    ancestor = next((path for path in chain if path.resolve() == Path(top)), None)
    if ancestor is None:
        raise Refusal(ROOT_THROUGH_SYMLINK)
    below = lexical.parts[len(ancestor.parts) :]
    linked = any(ancestor.joinpath(*below[: n + 1]).is_symlink() for n in range(len(below)))
    spelled = "".join(f"{part}/" for part in below)
    if linked or spelled != prefix.rstrip("\n"):
        raise Refusal(ROOT_THROUGH_SYMLINK)
    return spelled


def read_base(root: Path, base: str) -> str | None:
    """The base's `keelline.toml` at the project's own path, or `None` when git listed nothing
    there: the bootstrap, and the only answer that means it. Any other git failure fails the run.
    """
    if not BASE_REF.match(base):
        raise Refusal(BASE_SHAPE)
    prefix = repository_prefix(root)
    if base.startswith("refs/"):
        # Exactly this ref: when it is missing, git would take `refs/tags/<base>` instead.
        _read(root, "show-ref", "--verify", "--quiet", "--end-of-options", base)
    commit = _read(
        root, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{base}^{{commit}}"
    ).strip()
    path = f"{prefix}{CONFIG_FILE}"
    # Literal: a directory named like pathspec magic (`:(exclude)…`, `*`) is a name here.
    listed = _read(
        root,
        "--literal-pathspecs",
        "ls-tree",
        "--full-tree",
        "--name-only",
        "--end-of-options",
        commit,
        "--",
        path,
    )
    if not listed:
        return None
    return _read(root, "cat-file", "blob", "--end-of-options", f"{commit}:{path}")
