"""The public documents are held to a contract, the way the skills are (tests/skills).

`README.md` and `docs/methodology/` are read by people who have not read the code, which is
why nothing in them may be wrong in a way a test could have caught: a relative link that
does not resolve, a command row the parser does not accept, a command with no row, a
citation with no source, a source nothing cites, a principle with no statement of how well
it is backed. None of these is a matter of taste, so none is left to review.

No cross-module test imports (`tests/` is not a package): the three parser lines are the
same three `tests/skills/test_skills.py` has, on purpose.
"""

from __future__ import annotations

import argparse
import io
import re
import shlex
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, split_json_flag

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
METHODOLOGY = ROOT / "docs" / "methodology"
PRINCIPLES = METHODOLOGY / "principles.md"
SOURCES = METHODOLOGY / "sources.md"
# The freshness window `docs/methodology/README.md` states: a source published more than this
# many months before it was read must say `older` in its notes column. A working rule of the
# methodology, not a project budget, so it is a constant here and a sentence there.
FRESH_MONTHS = 2
# The three answers a principle may give to "how well is this backed", defined in
# docs/methodology/README.md. A fourth value is a wording change to that file first.
BACKING_LABELS = ("sourced", "measured", "thin")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
# `| S12 | title | 2026-08 | 2026-09 | https://… | cited for | notes |` — seven cells. The
# published cell is a month or the word `living` for a maintained page that carries no date.
_SOURCE_ROW = re.compile(
    r"^\| (S\d+) \| ([^|]+) \| (\d{4}-\d{2}|living) \| (\d{4}-\d{2}) \| "
    r"(https?://\S+) \| ([^|]+) \| ([^|]*)\|$",
    re.MULTILINE,
)
_CITATION = re.compile(r"\[(S\d+)\]")
_SECTION = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)
# The label, then a full stop, then whatever prose follows: `**Backing:** sourced. The mechanism…`.
# Capturing the bare word let `sourced for the budget` pass as `sourced` while the README says
# the label is chosen by the weakest link, so the stop is part of the grammar.
_BACKING = re.compile(r"^\*\*Backing:\*\* (\w+)\.", re.MULTILINE)


def prose(path: Path) -> str:
    return _FENCE.sub("", path.read_text(encoding="utf-8"))


def links_in(path: Path) -> list[str]:
    """Relative link targets in a document's prose; URLs, anchors and mail links are not
    the tree's to resolve."""
    return [
        target.split("#", 1)[0]
        for target in _LINK.findall(prose(path))
        if not target.startswith(("http://", "https://", "#", "mailto:"))
        and target.split("#", 1)[0]
    ]


def public_documents() -> list[Path]:
    return [README, ROOT / "docs" / "plans" / "README.md", *sorted(METHODOLOGY.glob("*.md"))]


def sources() -> dict[str, tuple[str, str, str, str, str, str]]:
    text = SOURCES.read_text(encoding="utf-8")
    return {row[0]: row[1:] for row in _SOURCE_ROW.findall(text)}


def principle_sections() -> list[tuple[str, str, str]]:
    """`(number, title, body)` per `## n. title` section of principles.md."""
    text = PRINCIPLES.read_text(encoding="utf-8")
    matches = list(_SECTION.finditer(text))
    return [
        (
            m.group(1),
            m.group(2),
            text[m.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)],
        )
        for i, m in enumerate(matches)
    ]


def _months(stamp: str) -> int:
    year, month = stamp.split("-")
    return int(year) * 12 + int(month)


# Vacuity floors, not coverage: the table has 32 rows and the principles 10 sections today,
# and these numbers say only "not empty enough to be a mistake". Pinning the exact counts
# would make every added source a test edit; the cited/citing tests below hold the content.
SOURCES_FLOOR = 20
PRINCIPLES_FLOOR = 8


def test_the_methodology_walks_are_not_empty() -> None:
    # The vacuity guard for every parametrised test below: an empty methodology directory
    # or an empty sources table passes them all vacuously. Named apart from the two gate
    # guards in `tests/test_neutral_wave2.py` so `-k` can pick one.
    assert PRINCIPLES in public_documents()
    assert len(sources()) >= SOURCES_FLOOR
    assert len(principle_sections()) >= PRINCIPLES_FLOOR


@pytest.mark.parametrize("path", public_documents(), ids=lambda p: str(p.relative_to(ROOT)))
def test_every_relative_link_resolves(path: Path) -> None:
    # Mutation: point one README link at `docs/methodolgy/` — that file's case reddens naming
    # the target.
    missing = [target for target in links_in(path) if not (path.parent / target).exists()]
    assert missing == [], missing


def test_every_source_row_parses_and_the_table_has_no_other_rows() -> None:
    # A row that does not match the grammar is invisible to every test below, which is how a
    # citation to it would look dangling and a fix would be to "loosen the regex". So the
    # table's row count is measured two ways and they must agree: every `| S` line is a row.
    text = SOURCES.read_text(encoding="utf-8")
    declared = [line for line in text.splitlines() if line.startswith("| S")]
    assert len(declared) == len(sources()), "a source row does not match the grammar"


def test_every_citation_resolves_and_every_source_is_cited() -> None:
    # Mutations: cite `[S99]` in a principle → the first assertion reddens; add a row `S98`
    # nothing cites → the second reddens. Both directions, because an uncited source is a
    # source someone meant to use and forgot, which is a claim left without its evidence.
    cited = set(_CITATION.findall(PRINCIPLES.read_text(encoding="utf-8")))
    cited |= set(_CITATION.findall((METHODOLOGY / "README.md").read_text(encoding="utf-8")))
    known = set(sources())
    assert cited - known == set(), sorted(cited - known)
    assert known - cited == set(), sorted(known - cited)


def test_a_source_older_than_the_window_says_so() -> None:
    # Mutation: delete the word `older` from one dated-2025 row's notes → reddens naming it.
    # A `living` page is fresh by definition of the `read` column, so the arithmetic skips it.
    late = [
        source_id
        for source_id, (_, published, read, _, _, notes) in sources().items()
        if published != "living"
        and _months(read) - _months(published) > FRESH_MONTHS
        and "older" not in notes
    ]
    assert late == [], late


def test_a_fresh_source_is_not_labelled_older() -> None:
    # The other direction: the label means something only if it is absent where it does not
    # apply. Mutation: write `older` into a `living` row's notes → reddens.
    wrong = [
        source_id
        for source_id, (_, published, read, _, _, notes) in sources().items()
        if "older" in notes
        and (published == "living" or _months(read) - _months(published) <= FRESH_MONTHS)
    ]
    assert wrong == [], wrong


def test_every_principle_states_its_backing_and_cites_or_measures() -> None:
    # Mutation: remove one `**Backing:**` line → that section is named. A `thin` principle
    # must still cite something or say why nothing exists; the citation rule here is that
    # every section carries at least one `[S<n>]`, and `thin` ones say in prose what the
    # citation does not establish — the README defines the labels.
    sections = principle_sections()
    unlabelled = [n for n, _, body in sections if not _BACKING.search(body)]
    assert unlabelled == [], unlabelled
    bad_label = [
        (n, m.group(1))
        for n, _, body in sections
        if (m := _BACKING.search(body)) and m.group(1) not in BACKING_LABELS
    ]
    assert bad_label == [], bad_label
    uncited = [n for n, _, body in sections if not _CITATION.search(body)]
    assert uncited == [], uncited


def test_principles_are_numbered_consecutively_from_one() -> None:
    # Cheap, and it is what makes `[principle 4]` in the README mean the same thing next
    # month. Mutation: renumber section 3 as 5 → reddens.
    numbers = [int(n) for n, _, _ in principle_sections()]
    assert numbers == list(range(1, len(numbers) + 1))


_COMMANDS_BLOCK = re.compile(r"^## Commands\n.*?^```text\n(.*?)^```", re.MULTILINE | re.DOTALL)


def readme_invocations() -> list[str]:
    """Every `keelline …` line in the README's Commands block, comments stripped."""
    match = _COMMANDS_BLOCK.search(README.read_text(encoding="utf-8"))
    assert match is not None, "README has no `## Commands` section with a ```text block"
    lines = (line.split("#", 1)[0].strip() for line in match.group(1).splitlines())
    return [line for line in lines if line.startswith("keelline ")]


def registered_commands() -> set[str]:
    """`group command` for every subcommand the real parser registers; a group with no
    subcommands (`hook <event>`) counts as its bare name."""
    parser = build_parser(discover_registrars())
    found: set[str] = set()
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for group, sub in action.choices.items():
            inner = [a for a in sub._actions if isinstance(a, argparse._SubParsersAction)]
            if not inner:
                found.add(group)
            for nested in inner:
                found.update(f"{group} {command}" for command in nested.choices)
    return found


# A vacuity floor, not a count of the commands this CLI ships: the parser registered twenty
# when this test was written, and the number is here so that a walk which found nothing — or
# half of them — cannot satisfy the subset check above it. A lane that ships a command raises
# the parser's count and leaves this alone.
REGISTERED_COMMANDS_FLOOR = 20


def test_the_parser_registers_what_this_test_expects_to_walk() -> None:
    # The mutation guard for the two tests below, and a pin on the walk's own mechanism:
    # `_SubParsersAction` is a private name, so the day argparse renames it this reddens
    # instead of `registered_commands()` returning an empty set that satisfies `<=`.
    found = registered_commands()
    assert {"memory index", "bugs check", "docs check", "plan check", "hook"} <= found
    assert len(found) >= REGISTERED_COMMANDS_FLOOR


def test_every_registered_command_has_a_readme_row() -> None:
    # Mutation: delete the `keelline docs trail` line from the README → reddens naming it.
    # This is the test that makes the README a shared file every lane owes a line to.
    named = {" ".join(line.split()[1:3]) for line in readme_invocations()}
    named |= {line.split()[1] for line in readme_invocations()}
    missing = sorted(command for command in registered_commands() if command not in named)
    assert missing == [], missing


def test_every_readme_row_parses() -> None:
    # Mutation: change the `bugs new` row's `--severity high` to `--severity critical` →
    # reddens naming the line. Not `--sev high`, which parses: argparse accepts any
    # unambiguous prefix of a long option, so an abbreviated flag is the one mistake in a
    # row this test cannot catch.
    parser = build_parser(discover_registrars())
    failed: list[str] = []
    for line in readme_invocations():
        argv, _ = split_json_flag(shlex.split(line)[1:])
        with redirect_stderr(io.StringIO()):
            try:
                parser.parse_args(argv)
            except SystemExit:
                failed.append(line)
    assert failed == [], failed


def test_the_readme_points_at_the_methodology_and_the_reference() -> None:
    # The two documents a reader is sent to; a README that lost either link would still pass
    # the link walk (it checks the links that exist). Mutation: remove the methodology link.
    text = prose(README)
    assert "docs/methodology/README.md" in text
    assert "docs/cli.md" in text
