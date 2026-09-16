"""One definition of what a ledger identifier looks like, from `[ledger] id_prefix`.

The source spelt `BR-` in eleven regular expressions and three format strings; a configurable
prefix means one object every reader and writer asks, so a prefix that changes changes all of
them together. A leaf module: the ledger, the plan lint (`Fixes BR-nnn`) and the memory graph
(`[[BR-nnn]]`) all read it, and none of them may import another's area. The prefix is
repository-controlled (§3): it is interpolated into patterns and filenames, so it is held to a
shape before either happens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from keelline.errors import Refusal

if TYPE_CHECKING:
    from keelline.config.schema import Config

# Upper-case letters and digits, one to eight characters, letter first. Not a budget: a cap on
# what may be interpolated into a regular expression and a filename, and the eight is what a
# `PREFIX-nnn.md` filename stays readable at.
PREFIX = re.compile(r"\A[A-Z][A-Z0-9]{0,7}\Z")
# Three digits or more: `renumber` and every reader enforce it, and the index guard the
# source grew was built around headings that fell short of it. The plan lint's `Fixes` rule
# reads the same constant, so the two cannot disagree about the minimum.
_DIGITS = r"\d{3,}"


@dataclass(frozen=True)
class Identifiers:
    prefix: str

    def __post_init__(self) -> None:
        if not PREFIX.match(self.prefix):
            raise Refusal(
                f"[ledger] id_prefix {self.prefix!r} must match {PREFIX.pattern}; "
                "it is interpolated into patterns and filenames"
            )

    @cached_property
    def exact(self) -> re.Pattern[str]:
        return re.compile(rf"\A{re.escape(self.prefix)}-({_DIGITS})\Z")

    @cached_property
    def mention(self) -> re.Pattern[str]:
        return re.compile(rf"\b{re.escape(self.prefix)}-{_DIGITS}\b")

    @cached_property
    def fixes(self) -> re.Pattern[str]:
        """The claim a plan makes that obliges it to carry a `Premise:` line."""
        return re.compile(rf"\bFixes\s+{re.escape(self.prefix)}-{_DIGITS}\b")

    def is_identifier(self, text: str) -> bool:
        return self.exact.match(text) is not None

    def number(self, identifier: str) -> int:
        match = self.exact.match(identifier)
        if match is None:
            raise Refusal(f"{identifier!r} is not a {self.shape} identifier")
        return int(match.group(1))

    def format(self, number: int) -> str:
        return f"{self.prefix}-{number:03d}"

    @property
    def shape(self) -> str:
        """How a message spells the contract: `BR-nnn`."""
        return f"{self.prefix}-nnn"


def identifiers(config: Config) -> Identifiers:
    return Identifiers(config.ledger.id_prefix)
