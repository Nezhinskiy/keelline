"""`release notes`: assemble CHANGELOG.md from `changelog.d/` through towncrier.

The command is a wrapper and nothing more: towncrier owns the rendering, `pyproject.toml`'s
`[tool.towncrier]` owns the format, and this module owns two refusals — the version must be
the project's, and a missing towncrier is named as the development dependency it is.
"""

from __future__ import annotations

from pathlib import Path

from keelline.errors import Failure, Refusal
from keelline.release.versions import collect
from keelline.runner import NOT_FOUND, Runner


def build(root: Path, *, version: str, draft: bool, runner: Runner) -> str:
    current = collect(root)["pyproject.toml"]
    if version != current:
        raise Refusal(
            f"--version {version} is not the project's ({current!r}); set the version "
            "everywhere first — `keelline release check` names the six places — and then "
            "assemble the changelog under it"
        )
    argv = ["towncrier", "build", "--version", version, "--yes"] + (["--draft"] if draft else [])
    done = runner.run(argv, root)
    if done.code == NOT_FOUND:
        raise Failure(
            "towncrier could not be run; it is a development dependency, and `uv sync` installs it"
        )
    if done.code != 0:
        raise Failure(f"towncrier exited {done.code}: {done.stderr.strip()}")
    return done.stdout
