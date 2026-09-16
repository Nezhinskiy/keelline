"""The advisory memory link graph (Premise 11): every `[[link]]` resolves to a document in the
store, no link is immediately repeated, no ledger identifier is bracketed. Advice, never a
verdict: the store is shared by every session on the machine.

Nothing here is a grammar of its own: the wiki-link pattern is the memory area's
(`WIKI_LINK` on the C3 surface), the identifier grammar is `keelline.identifiers`, and what
counts as prose is `keelline.prose`'s.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from keelline.findings import Finding
from keelline.identifiers import identifiers
from keelline.memory.api import WIKI_LINK, Store, walk
from keelline.prose import blank_code_spans, blank_fences

if TYPE_CHECKING:
    from keelline.config.schema import Config

# Lookahead, not a plain pair match: findall consumes without overlap, so in `[[a]] [[b]] [[b]]`
# the a-b pair would eat the left half of the real b-b pair. The separator class covers the
# list forms a bulk repoint collapses into: `, `, `, and `, ` or `. Built from `WIKI_LINK` so
# the two cannot disagree about what a link is.
_REPEAT = re.compile(rf"{WIKI_LINK.pattern}(?:[,\s]|\band\b|\bor\b)*(?={WIKI_LINK.pattern})")


def check_memory_graph(store: Store, config: Config) -> list[Finding]:
    groups = [g for g in config.memory.groups if g in store.groups]
    walked = walk(store.path, groups)
    linkable = {p.stem for p in store.path.glob("*.md")}
    for group in groups:
        linkable |= {p.stem for p in (store.path / group).glob("*.md")}
    ids = identifiers(config)
    found: list[Finding] = []
    for note in walked.notes:
        where = note.path.relative_to(store.path).as_posix()
        # Fences first (they can contain backticks), then spans; the span placeholder keeps
        # `[[a]] `x` [[a]]` from reading as a repeat.
        text = blank_code_spans(blank_fences(note.body))
        for target in WIKI_LINK.findall(text):
            if ids.is_identifier(target):
                found.append(Finding("bracketed-identifier", where, None, target))
            elif target not in linkable:
                found.append(Finding("dead-wiki-link", where, None, target))
        for first, repeat in _REPEAT.findall(text):
            if first == repeat:
                found.append(Finding("repeated-link", where, None, first))
    return found
