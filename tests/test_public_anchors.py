"""Shipped code and documents cite what a reader here can open, and nothing else.

The design these modules were built against lives in a private repository. A `§9.1` or a
`(D7)` in a docstring therefore points a reader at a page they cannot open: it looks like a
reference and carries none of the content. Three hundred and nine lines in eighty-seven files
did it before this gate — in `src/`, in `docs/cli.md`, in the preset and in the hook wrapper.
The rule is to say what the section says, in a few words, or to cite an anchor that exists in
this repository — `docs/cli.md#…`, `CONTRIBUTING.md`, or a principle of
`docs/methodology/principles.md` by its number.

**`docs/plans/` is exempt, and on purpose.** A plan is a historical record of work argued from
the design, and it keeps the ids it argued with; `CONTRIBUTING.md` says its references cannot
be followed from here. Everything else a user installs or reads is walked.

The arms are deliberately wider than "a parenthesised id". The ids were written bare as often
as in brackets — `D7: a cap, not a config key`, `DP3 makes it trusted by construction`, `C5's
exit 2` — and an arm that saw only one spelling would have let most of the class back in. What
the width costs is a rewrite: a future sentence that needs a bare `D3` or `P1` for some other
reason says it another way.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_neutral import ROOT, tracked_files

# What ships or is read as documentation: the package, the plugin's own trees and the two
# top-level documents a contributor is sent to. `tests/` and `scripts/` are the maintainers'
# and are not walked; `.github/` is left to the reviewer, because `RELEASING.md §3` in a
# workflow comment is a public anchor that the section arm below cannot tell from a private one.
SCOPE = ("src", "skills", "docs", "hooks", "agents")
TOP_LEVEL = ("README.md", "CONTRIBUTING.md")
EXEMPT = ("docs/plans",)

# Each arm is named so a hit says what it is.
CITATIONS = (
    ("design section", re.compile(r"§\s*\d")),
    # The two-letter prefixes are unambiguous; the one-letter ones are held to the numbers the
    # design and its plans used, and `C0` stays legal because it is the Unicode name of the
    # control characters `tomlout` escapes.
    ("decision id", re.compile(r"\b(?:DC|DP|OD)\d+\b|\b[DP]\d{1,2}\b|\bC[1-9]\b")),
    # Whatever prefix a later plan invents, it arrives in brackets at the end of a sentence.
    ("bracketed id", re.compile(r"\([A-Z]{1,2}\d{1,2}(?:,\s*[A-Z]{1,2}\d{1,2})*\)")),
    # The design's measurement log, cited as `Findings → S6`.
    ("design finding", re.compile(r"Findings\s*→")),
    # A plan's own headings, which a module quoted as if the reader had the plan open: "Premise 2
    # of the lane's plan", "by the Global Constraints' own list". `CONTRIBUTING.md` holds the
    # rules a contributor can read; a principle holds the argument.
    ("plan section", re.compile(r"\bPremise \d|Global Constraint")),
)


def in_scope(path: Path) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    if any(relative == exempt or relative.startswith(exempt + "/") for exempt in EXEMPT):
        return False
    return relative in TOP_LEVEL or relative.split("/", 1)[0] in SCOPE


def citations(text: str) -> list[tuple[int, str, str]]:
    """Every private citation in the text, as `(line number, arm name, matched text)`."""
    found: list[tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in CITATIONS:
            found.extend((number, name, match.group()) for match in pattern.finditer(line))
    return found


def walked() -> list[Path]:
    return [path for path in tracked_files() if in_scope(path)]


def test_the_citation_gate_discriminates() -> None:
    # Break any arm — widen it into silence, or drop a spelling — and one of these goes the
    # wrong way. The negatives are the neighbours the arms must not take: the public source
    # list's `[S27]`, a principle by number, a Unicode control class, a version, a digest name.
    for planted in (
        "the store's own §9.1 checks",
        "§ 5.3",
        "(D7)",
        "D7: a cap, not a config key",
        "DC3 says the registry stamps it",
        "DP3 makes the overlay trusted",
        "OD5 as a table",
        "the argument P10 makes",
        "C5's exit 2",
        "(R5, D15)",
        "(E3)",
        "Findings → S6 did not reproduce",
        "the dispatcher banks it (Premise 2)",
        "repository-authored by the Global Constraints' own list",
    ):
        assert citations(planted), planted
    for clean in (
        "sourced [S3] [S7], and that is the",
        "principle 5 says a repository is untrusted input",
        "see docs/cli.md#keelline-init",
        "Every other C0 control and DEL",
        "Python 3.11, 3.12 and 3.13",
        "a sha256 digest, MD5 never",
        "exit code 2 (a refusal)",
    ):
        assert citations(clean) == [], clean


def test_the_citation_walk_reads_what_ships_and_skips_the_plans() -> None:
    # The non-vacuity guard for the walk below: one named file from every tree in scope, and the
    # exemption shown to be real — a plan is tracked, and it is not walked.
    names = {path.relative_to(ROOT).as_posix() for path in walked()}
    for wanted in (
        "README.md",
        "CONTRIBUTING.md",
        "src/keelline/cli.py",
        "src/keelline/presets/recommended.toml",
        "docs/cli.md",
        "docs/methodology/principles.md",
        "skills/README.md",
        "hooks/run-hook.sh",
        "agents/code-navigator.md",
    ):
        assert wanted in names, wanted
    plans = [p for p in tracked_files() if p.relative_to(ROOT).as_posix().startswith("docs/plans/")]
    assert plans
    assert not names.intersection(p.relative_to(ROOT).as_posix() for p in plans)


def test_no_shipped_file_cites_the_private_design() -> None:
    # One test over the whole walk rather than one per file, so a regression reads as a list of
    # `path:line` a contributor can work through instead of a wall of parametrised cases.
    hits: list[str] = []
    # No `UnicodeDecodeError` handler: nothing in scope is binary, and a walk that skipped what it
    # could not read would go green by reading nothing.
    for path in walked():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        hits.extend(f"{relative}:{n}: {arm} {found!r}" for n, arm, found in citations(text))
    assert hits == [], "\n".join(hits)
