"""Run git inside a project root and read failure as "nothing found".

Three lines over `keelline.gitenv.git_run`, which owns the subprocess, the scrubbed
environment and the bound; every caller here treats an empty answer as an empty set.
"""

from __future__ import annotations

from pathlib import Path

from keelline.gitenv import git_run

# Wall-clock bound on one local git query (a named cap, not a config key — no shipped file
# changes with it). Wider than `gitenv.GIT_TIMEOUT_SECONDS` because `log --all` over a long
# history is not a five-second `rev-parse`; the allocator's `fetch` has its own bound.
QUERY_TIMEOUT_SECONDS = 30


def git_output(root: Path, *args: str, timeout: float = QUERY_TIMEOUT_SECONDS) -> str:
    """stdout of `git -C root args`, or `""` on any failure."""
    code, out = git_run(root, *args, timeout=timeout)
    return out if code == 0 else ""
