"""A pull request's checkout, as the tests that read a base see it: a clone on branch `change`
of an upstream whose `main` carries a `keelline.toml`.

`tests/project/repos.py` is not reused: its repository has a fake `origin` URL and no
remote-tracking ref, and the remote-tracking ref is exactly what a base is read from.
"""

from __future__ import annotations

import os
from pathlib import Path

from tests.gitfixture import git

AGENTS = "# widget\n\n## Current status\n\n- Started.\n"


def commit(root: Path, subject: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-qm", subject)


def clone(tmp_path: Path, base: str | bytes, *, under: str = "") -> Path:
    """The clone; `under` is the project's directory inside the repository, `""` for the root.

    `base` is the upstream's `keelline.toml`; bytes for a document that is not UTF-8.
    """
    upstream = tmp_path / "upstream"
    (upstream / under).mkdir(parents=True)
    git(upstream, "init", "-q", "-b", "main")
    document = upstream / under / "keelline.toml"
    if isinstance(base, bytes):
        document.write_bytes(base)
    else:
        document.write_text(base, encoding="utf-8")
    (upstream / under / "AGENTS.md").write_text(AGENTS, encoding="utf-8")
    commit(upstream, "chore: base")
    project = tmp_path / "project"
    git(tmp_path, "clone", "-q", str(upstream), str(project))
    git(project, "checkout", "-q", "-b", "change")
    return project


def shadow(project: Path, name: str) -> None:
    """A tag spelled `name`, on a commit that carries no `keelline.toml` at all."""
    empty = git(project, "hash-object", "-t", "tree", "-w", os.devnull).strip()
    git(project, "tag", name, git(project, "commit-tree", empty, "-m", "nothing").strip())
