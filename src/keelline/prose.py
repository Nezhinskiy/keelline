"""The one grammar for "a backticked path in hand-written prose".

The plan lint and the memory reference guard read different documents for different reasons
and ask them the same question: which backticked spans claim that a path exists. In the
source they held two copies of that question, and the copies had already drifted — one
accepted `.ts`/`.tsx` and the other did not, so in a repository whose front end is TypeScript
a plan naming a dead `.ts` module got no reference check at all, while the newer module's
docstring asserted it shared a grammar it did not.

Three rules live here, and each is a decision rather than a default:

* the extension list, because a backticked span is a path claim only when it looks like a
  file this repository stores. The whole span is the path, so a shell command or a URL —
  both of which carry characters this class excludes — cannot match, and a trailing `:12` or
  `::name` is a location within the file rather than part of its name;
* fences are BLANKED, not deleted. Fenced code is fixture text and not prose, and deleting a
  block shifts every line below it upward by the block's height, so every report under a
  fence named a line that was not the line;
* a bare filename is prose. `config.py` is a sentence about a file, not a claim about where
  one is, and reading it as a path makes every such mention unresolvable.

A leaf module: `docs.plans`, `docs.graph`, `docs.hygiene` and `memory.refs` import it, and
none may import another's area.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

REFERENCE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|sh|md|json|ya?ml|toml|tsx?))(?::\d+|::[\w.]+)?`")
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*$", re.MULTILINE | re.DOTALL)
# Inline code, single-line so a stray backtick cannot swallow the lines after it. Blanked
# AFTER fences (a fence can contain backticks).
CODE_SPAN = re.compile(r"`[^`\n]*`")


def blank_fences(text: str) -> str:
    """``text`` with each fenced block replaced by its own height in blank lines."""

    return FENCE.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def blank_code_spans(text: str, placeholder: str = "\x00") -> str:
    """``text`` with each inline code span replaced by ``placeholder``.

    A placeholder, not a deletion: removing a span leaves its neighbours adjacent, so
    `[[a]] `x` [[a]]` would read as a repeated link. Not for the readers of backticked paths
    (`path_references` reads spans; this erases them) — the memory graph check is the caller.
    """
    return CODE_SPAN.sub(placeholder, text)


def path_references(line: str) -> Iterator[str]:
    """Every backticked span in ``line`` that claims a path; bare filenames are prose."""

    for match in REFERENCE.finditer(line):
        target = match.group(1)
        if "/" in target:
            yield target
