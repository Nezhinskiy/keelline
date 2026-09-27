"""How a name the repository chose may be printed on a line a terminal or a CI runner reads.

A repository chooses its own file names, note names, `memory.groups` entries and TOML keys, and
any of them may hold a line break followed by `::error::…`, which a GitHub Actions runner reads
from a job's output as a workflow command, or an escape sequence, which drives the reader's
terminal. `trust.wrap` marks such text as data for a model and escapes no byte for either of
those readers, so a printed line needs one of the two bounds below. Both answer from
`PATH_VALUE`, the one grammar a path may print in: ASCII letters, digits, `.`, `_` and `-` in
`/`-separated segments. A name inside it prints as itself, so ordinary output is unchanged.

- `printable` withholds a name outside the grammar. It is for a line whose command also carries
  the name in `--json`, and for any line a model reads, where a name that holds spaces could
  carry readable prose.
- `quoted` escapes a name outside the grammar with `repr`. It is for a refusal, which has no
  `--json` behind it, where withholding the name would leave the operator nothing to rename.
"""

from __future__ import annotations

from collections.abc import Callable

from keelline.config.schema import PATH_VALUE

# What a name outside `PATH_VALUE` prints as on a line whose command carries it in `--json`.
# Fixed text, and it says where the name itself went.
UNPRINTABLE = "<unprintable name; see --json>"


def printable(name: str, withheld: str = UNPRINTABLE) -> str:
    """`name` itself inside the path grammar, `withheld` outside it. A caller whose output has
    no `--json` to point at passes a `withheld` of its own."""
    return name if PATH_VALUE.match(name) else withheld


def quoted(name: str) -> str:
    """`name` itself inside the path grammar, its `repr` outside it.

    `repr` escapes every line break and control character, so the name arrives whole, cannot
    start a line and cannot drive a terminal."""
    return name if PATH_VALUE.match(name) else repr(name)


# How many characters of a name a refusal prints before it clips the rest to a count. A named cap
# (CONTRIBUTING.md#named-caps), and `docs/cli.md` states the number for the refusals that use it
# (`docs trail`'s stale `[states]` keys and its `[[theme]]` label, and the memory store's
# unresolved groups), so a change to either is a change to both. `quoted` escapes a name and does
# not bound its length, and a TOML key, a label or a group is bounded in length by nothing, so
# without this a refusal's line is as long as the repository makes one name. 120 is well past any
# name an operator would type, and short enough that the start still says which one it is.
CLIPPED_CHARS = 120


def clipped(name: str, show: Callable[[str], str] = quoted) -> str:
    """`show(name)`, or past `CLIPPED_CHARS` the first characters through `show` and the
    length: `…(N chars)`. For a refusal, where the name is the only channel and must still be
    identifiable, and where no bound on its length exists upstream."""
    if len(name) <= CLIPPED_CHARS:
        return show(name)
    return f"{show(name[:CLIPPED_CHARS])}…({len(name)} chars)"
