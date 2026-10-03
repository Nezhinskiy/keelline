"""The one recording `stayfixed.runner.Runner` the suite hands the code under test.

Thirteen test modules each defined their own, and eleven of the copies answered the same
question — record the argv, answer with a fixed `Completed` — with different defaults: `0` or
`2` for the exit code, an empty stdout or a tag listing, an argv list or an `(argv, cwd)` pair
for the record, and two of them (in `tests/overlay/test_create.py` and
`tests/setup/test_setup.py`) the same prefix-scripted answer table written out twice, the second
without the first's `cwds`.
Here the defaults are parameters, so a module says what its runner answers at the call site
rather than in a private class a reader has to open.

Two fakes stay where they are because they answer a different question, and each says why in
its own docstring: `tests/guards/test_attribute.py`'s answers by the tree it was run in and
snapshots that tree, and `tests/overlay/test_publish.py`'s models GitHub's state and materialises
the clone the publisher writes into. `tests.gitfixture.LsRemote` is this recorder with the exit
code `git ls-remote --exit-code` gives for no matching tag, named because that is the question
most of the suite's runners are asked.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from stayfixed.runner import Completed


@dataclass(kw_only=True)
class Recorder:
    """Records every argv and working directory, and answers from a script or else the default.

    `answers` maps a space-joined argv prefix to its answer, and the longest key that prefixes
    the argv wins: a key of `gh` means "this binary", and a longer one scripts a single question —
    the template probe and the repository creation are both `gh`, and they have to be answered
    apart for a test to say which template `create` chose. Keyed on `argv[0]` alone, `{"claude":
    ...}` used to answer *every* `claude` call identically, so `setup`'s install-failure branch was
    unreachable: a script that failed the install failed the `marketplace add` first. An argv no
    key prefixes gets `Completed(code, stdout, stderr)`.

    `on_call` runs before the answer is chosen, for a test whose fixture must exist by the time the
    code under test reads it — a template's files where `gh repo create --clone` would have put
    them.

    Keyword-only, so a call site names the default it changes rather than relying on an order.
    """

    code: int = 0
    stdout: str = ""
    stderr: str = ""
    answers: dict[str, Completed] = field(default_factory=dict)
    on_call: Callable[[list[str], Path], None] | None = None
    calls: list[list[str]] = field(default_factory=list)
    cwds: list[Path] = field(default_factory=list)

    def launch(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        self.cwds.append(cwd)
        if self.on_call is not None:
            self.on_call(argv, cwd)
        for width in range(len(argv), 0, -1):
            answer = self.answers.get(" ".join(argv[:width]))
            if answer is not None:
                return answer
        return Completed(self.code, self.stdout, self.stderr)
