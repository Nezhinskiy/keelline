"""Run git inside a project root and read failure as "nothing found".

Three lines over `keelline.gitenv.git_run`, which owns the subprocess, the scrubbed
environment and the bound. Only a question whose empty answer is safe belongs here: the scan's
top-level probe, where no answer means "walk the disk instead". The listing and the allocator's
history call `git_run` themselves, because for them no answer read as an empty set scanned no
file, or counted no other ref.
"""

from __future__ import annotations

from pathlib import Path

from keelline.gitenv import git_run

# Wall-clock bound on one local git query (D7: a cap, not a config key — no shipped file
# changes with it). Wider than `gitenv.GIT_TIMEOUT_SECONDS` because `log --all` over a long
# history is not a five-second `rev-parse`; the allocator's `fetch` has its own bound.
QUERY_TIMEOUT_SECONDS = 30


def git_output(root: Path, *args: str, timeout: float = QUERY_TIMEOUT_SECONDS) -> str:
    """stdout of `git -C root args`, or `""` on any failure."""
    code, out = git_run(root, *args, timeout=timeout)
    return out if code == 0 else ""
