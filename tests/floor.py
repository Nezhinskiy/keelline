"""The floor the suite puts under every `git` the product runs, in a test's own process and in
every `keelline` a test starts as a separate one.

The product's own bounds on `git` are sized for a machine doing one thing. Under a full `-n auto`
run beside other sessions' work a five-second `rev-parse` and a two-second `status` ran out, the
caller read that as no answer, and the test failed for the machine's load rather than for the
code — and a verdict decided by load is one the oracle reads as a caught mutation.
`tests/conftest.py` used to raise the floor by assignment, which reaches only the test's own
process: a `keelline` started through the launcher, the hook wrapper or a git hook's shim still
ran under the bare five-second bound, failed the suite at random at load averages of eight to
eleven, and passed when run alone.

So the floor travels the one way that crosses a process boundary: `gitenv.FLOOR_VARIABLE`, set
in this process's environment for every test by `tests/conftest.py`. A spawner that inherits
`os.environ` passes it on as it is. A spawner that builds its child's environment — most of them,
because a child must not read the developer's own `KEELLINE_*` or `HOME` — adds `floor_env()`
after it has stripped what it strips. `gitenv` explains why the product may honour the variable.
"""

from __future__ import annotations

import os

from keelline import gitenv

SUITE_GIT_FLOOR_SECONDS = 60.0


def floor_env() -> dict[str, str]:
    """The floor as the one environment entry a spawned `keelline` needs to inherit it.

    Read from this process's environment rather than spelled again, so a test that removed the
    floor to exercise a bound running out gives its children none either: one channel, one
    state, in every process the test runs.
    """
    value = os.environ.get(gitenv.FLOOR_VARIABLE)
    return {} if value is None else {gitenv.FLOOR_VARIABLE: value}
