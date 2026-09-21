"""The public documents are held to a contract, the way the skills are (tests/skills).

`README.md` and `docs/methodology/` are read by people who have not read the code, which is
why nothing in them may be wrong in a way a test could have caught: a relative link that
does not resolve, a command row the parser does not accept, a command with no row, a
citation with no source, a source nothing cites, a principle with no statement of how well
it is backed. None of these is a matter of taste, so none is left to review.

The three parser lines are the same three `tests/skills/test_skills.py` has, on purpose:
two modules asking the real parser the same question is two claims, and collapsing them would
make one of the two documents provable only through the other. This used to forbid a cross-module
import on the grounds that the test tree was not importable, which was false in both halves:
`tests/__init__.py` is tracked, nine modules import across it, and `CONTRIBUTING.md` carries no
such rule. `tests/snapshot.py` is where a helper two modules share
belongs.
"""

from __future__ import annotations

import argparse
import inspect
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


TESTS = ROOT / "tests"


def test_no_module_claims_the_test_tree_cannot_share_a_helper() -> None:
    """The sentence that authorised the duplication this module exists to end.

    Three modules said, in as many words, that a helper was copied rather than imported
    because the test tree was not importable as a package and CONTRIBUTING forbade a
    cross-module import. Both halves are false: `tests/__init__.py` is tracked, `CONTRIBUTING.md`
    carries no such rule,
    and `tests/overlay/test_upgrade.py` imports the very class one of those comments said it
    could not. What it cost, measured at the time: the hardened-`git` helper defined in 26
    modules, six of them already drifted, while `tests/snapshot.py` published it.

    In a tree whose whole discipline is that a comment is evidence, a false comment that
    *authorises* a practice is worse than the practice. So the claim is a finding, and the
    import that disproves it is asserted to still exist.
    """
    # Mutation: put the sentence back into `tests/test_documents.py` -> reddens naming it.
    assert (TESTS / "__init__.py").is_file(), "tests/ stopped being a package"
    modules = sorted(TESTS.rglob("test_*.py"))
    # The walk's floor before anything is asserted about it: a glob that matched nothing would
    # make both lists empty and the claim check vacuously true.
    assert len(modules) >= 40, len(modules)
    texts = {module: module.read_text(encoding="utf-8") for module in modules}
    importers = sorted(m.name for m, text in texts.items() if "\nfrom tests." in text)
    # And the disproof is live rather than remembered: eight or more modules really do import
    # across the package today (nine when this was written).
    assert len(importers) >= 8, importers
    # Assembled rather than written out, because this module is inside the walk and a literal
    # needle would match the line that holds it — the guard would then report itself for ever.
    needle = "is not a " + "package"
    claims = sorted(str(m.relative_to(TESTS)) for m, text in texts.items() if needle in text)
    assert claims == [], claims


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


def test_every_principle_states_its_backing_and_cites_a_source() -> None:
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


# `docs/methodology/README.md` states the thin count in prose and in words — `Three of the ten
# are thin` — because it is prose a person reads, not a table. The count is read off that
# sentence rather than written here, so an honest relabelling is one edit in the document it
# describes and none in this file; the test holds only that the two agree.
_THIN_CLAIM = re.compile(r"(\w+) of the (\w+) are thin", re.IGNORECASE)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def test_the_stated_thin_count_matches_the_labels() -> None:
    # A prose count in a tree that tests everything else it could: a fourth `thin` label, or a
    # third one relabelled, falsifies the sentence silently. Mutation: relabel one `sourced`
    # principle `thin` → reddens on the count.
    text = (METHODOLOGY / "README.md").read_text(encoding="utf-8")
    claim = _THIN_CLAIM.search(text)
    assert claim is not None, "docs/methodology/README.md no longer says how many are thin"
    stated_thin = _NUMBER_WORDS[claim.group(1).lower()]
    stated_total = _NUMBER_WORDS[claim.group(2).lower()]
    labels = [m.group(1) for _, _, body in principle_sections() if (m := _BACKING.search(body))]
    assert labels.count("thin") == stated_thin, labels
    # The other half of the sentence: `of the ten` is a count of principles, not of labels.
    assert len(principle_sections()) == stated_total


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


# `--json`'s one cross-command promise, in the README's Exit-codes paragraph. The sentence
# named four commands while five emit the key — `memory refs` was missing — so a reader
# scripting against it would have treated a `findings` list as "this command does not report
# findings". Bound to the real parser's functions rather than to a second hand-written list.
_FINDINGS_SENTENCE = re.compile(
    r"The commands that report a list of\nfindings — (.+?) —\nall spell it `findings`", re.MULTILINE
)


def command_functions() -> dict[str, object]:
    """`group command` -> the `run_*` callable the real parser dispatches to."""
    parser = build_parser(discover_registrars())
    found: dict[str, object] = {}
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for group, sub in action.choices.items():
            inner = [a for a in sub._actions if isinstance(a, argparse._SubParsersAction)]
            if not inner:
                func = sub.get_default("func")
                if func is not None:
                    found[group] = func
            for nested in inner:
                for command, leaf in nested.choices.items():
                    func = leaf.get_default("func")
                    if func is not None:
                        found[f"{group} {command}"] = func
    return found


def test_the_readme_names_every_command_whose_json_carries_findings() -> None:
    # Mutation: drop `memory refs` from the README sentence -> reddens naming it.
    # The floor first: a walk that resolved no functions would make the comparison below
    # vacuously true, and a regex that stopped matching would look the same.
    functions = command_functions()
    assert len(functions) >= REGISTERED_COMMANDS_FLOOR, sorted(functions)
    emitting = {
        name
        for name, func in functions.items()
        if '"findings":' in inspect.getsource(func)  # type: ignore[arg-type]
    }
    assert len(emitting) >= 5, sorted(emitting)
    match = _FINDINGS_SENTENCE.search(README.read_text(encoding="utf-8"))
    assert match is not None, "README's --json paragraph no longer names the findings commands"
    named = set(re.findall(r"`([^`]+)`", match.group(1)))
    assert named == emitting, (sorted(named), sorted(emitting))


RELEASING = ROOT / "RELEASING.md"
INSTALL_BEGIN = "<!-- release-install:begin -->"
INSTALL_END = "<!-- release-install:end -->"


def test_the_release_step_and_the_readme_agree_on_what_it_replaces() -> None:
    """The release commit is meant to be an edit, and the edit had no stated extent.

    `RELEASING.md` step 5 said to replace "the **Nothing is released yet.** paragraph" with the
    text in the HTML comment above it — but that replacement carries its own two code blocks
    and says "Both commands below install that release". Swapping only the paragraph left the
    untagged `/plugin marketplace add …` and `uv tool install git+https://…` blocks standing
    underneath the tagged ones, plus a "From the first release on, the same command takes the
    tag" paragraph that the release had just made false: two competing install commands and a
    stale promise, in the first screen a new adopter reads. `release check` cannot see README
    examples, and `RELEASING.md` says so, so nothing else catches it.

    The extent is markers now, and this holds the three things that make markers work.

    Mutation (declared): the begin marker is dropped from `README.md` -> this reddens.
    """
    readme = README.read_text(encoding="utf-8")
    releasing = RELEASING.read_text(encoding="utf-8")
    # One of each, in order, so the region is a region.
    assert readme.count(INSTALL_BEGIN) == 1, readme.count(INSTALL_BEGIN)
    assert readme.count(INSTALL_END) == 1, readme.count(INSTALL_END)
    assert readme.index(INSTALL_BEGIN) < readme.index(INSTALL_END)
    # The region really holds the untagged install commands — the bytes the release replaces.
    region = readme[readme.index(INSTALL_BEGIN) : readme.index(INSTALL_END)]
    assert "Nothing is released yet." in region, region[:200]
    assert "/plugin marketplace add" in region, region[:200]
    assert "uv tool install git+" in region, region[:200]
    assert "From the first release on" in region, region[:200]
    # And the step names the markers, rather than describing an extent in prose.
    assert INSTALL_BEGIN in releasing, "RELEASING.md step 5 no longer names the begin marker"
    assert INSTALL_END in releasing, "RELEASING.md step 5 no longer names the end marker"


def test_the_readme_points_at_the_methodology_and_the_reference() -> None:
    # The two documents a reader is sent to; a README that lost either link would still pass
    # the link walk (it checks the links that exist). Mutation: remove the methodology link.
    text = prose(README)
    assert "docs/methodology/README.md" in text
    assert "docs/cli.md" in text


CLI_REFERENCE = ROOT / "docs" / "cli.md"
# The section Task 6 created and two later waves anchor on. Everything between its heading and
# the next `## ` heading, so a table moved out of it stops being checked loudly rather than
# quietly.
_SHARED_FLAGS_SECTION = re.compile(r"^## Shared flags\n(.*?)(?=^## )", re.MULTILINE | re.DOTALL)
_TABLE_ROW = re.compile(r"^\| (?!Flag |Command and flag |---)(.+?) \| (.+?) \|$", re.MULTILINE)


def test_the_shared_flag_tables_are_the_constants_and_not_a_second_spelling() -> None:
    # Fix round 1, item 4. DC4's premise is that no sentence is spelled by hand, and the
    # section this task added spelled all nine of them a second time in a document nothing
    # checked — re-creating, one file over, exactly the drift the task exists to remove. Held
    # row by row to `keelline.command`'s constants, the same way the README's Commands block is
    # held to the real parser above.
    #
    # Mutation: change the `--machine` row's cell in `docs/cli.md` → reddens naming the row.
    from keelline.command import (
        ATTACH_CHECK_HELP,
        CHECK_HELP,
        DRY_RUN_HELP,
        HOME_HELP,
        INSTANCE_DIR_HELP,
        MACHINE_HELP,
        OVERLAY_ROOT_HELP,
        ROOT_HELP,
        SETUP_MACHINE_HELP,
        SETUP_ROOT_HELP,
        STORE_HELP,
    )

    expected = {
        "`--root`": ROOT_HELP,
        "`--machine`": MACHINE_HELP,
        "`--store`": STORE_HELP,
        "`--dry-run`": DRY_RUN_HELP,
        "`--home`": HOME_HELP,
        "`--check`": CHECK_HELP,
        "`keelline overlay create --root`": INSTANCE_DIR_HELP,
        "`keelline overlay init --root`, `keelline overlay upgrade --root`": OVERLAY_ROOT_HELP,
        "`keelline setup --root`": SETUP_ROOT_HELP,
        "`keelline setup --machine`": SETUP_MACHINE_HELP,
        "`keelline attach --check`": ATTACH_CHECK_HELP,
    }
    section = _SHARED_FLAGS_SECTION.search(CLI_REFERENCE.read_text(encoding="utf-8"))
    assert section is not None, "docs/cli.md has no `## Shared flags` section"
    rows = dict(_TABLE_ROW.findall(section.group(1)))
    # The walk's own floor, before anything is compared: a regex that matched nothing would
    # make every comparison below vacuously true, and a section that lost a table would look
    # exactly like one that never had it.
    assert len(rows) == len(expected), rows
    assert rows == expected, {
        flag: (rows.get(flag), sentence)
        for flag, sentence in expected.items()
        if rows.get(flag) != sentence
    }


# The configuration block in `docs/cli.md` is introduced as the grammar, and the loader
# *refuses* an unknown section — so a section the block leaves out reads to a reader as a key
# that is invalid. Three of the nine were missing (`[artifacts]`, `[ci]`, `[commit_messages]`),
# which is the drift a binding prevents. `## Configuration` down to the next `## ` heading.
# The FIRST fenced `toml` block under `## Configuration` — the `keelline.toml` one. The section
# carries a second block, the machine file, whose `[personal]` and `[overlay]` are not sections
# of this grammar at all; scoping to the first block is what keeps the two apart.
_CONFIGURATION_BLOCK = re.compile(
    r"^## Configuration\n.*?^```toml\n(.*?)^```", re.MULTILINE | re.DOTALL
)
_TOML_HEADER = re.compile(r"^\[([a-z_]+)\]", re.MULTILINE)


def test_the_configuration_block_shows_every_section_the_loader_accepts() -> None:
    # Mutation: drop the `[ci]` header from `docs/cli.md`'s block -> reddens naming it.
    from keelline.config.loader import SECTIONS

    section = _CONFIGURATION_BLOCK.search(CLI_REFERENCE.read_text(encoding="utf-8"))
    assert section is not None, "docs/cli.md's `## Configuration` has no ```toml block"
    # The walk's floor before anything is compared: a regex that matched no headers would make
    # the set comparison below vacuously a subset in one direction and empty in the other.
    shown = _TOML_HEADER.findall(section.group(1))
    assert len(shown) >= len(SECTIONS), shown
    assert set(shown) == set(SECTIONS), (sorted(set(shown)), sorted(SECTIONS))


# `plan check`'s rule count, stated in the reference and emitted by `docs/plans.py`. The
# sentence said "Four rules" and then listed five, in one breath, for as long as the fifth rule
# has existed. `base-unresolvable` is the refusal, not one of the rules the sentence counts.
_PLAN_RULES_SENTENCE = re.compile(r"\. (\w+) rules, each from a\nretrospective:")
_PLAN_FINDING_CODE = re.compile(r'Finding\("([a-z-]+)"')
PLAN_REFUSAL_CODE = "base-unresolvable"


def test_the_plan_rule_count_is_the_number_of_rules_plan_check_emits() -> None:
    # Mutation: change `Five rules` back to `Four rules` in `docs/cli.md` -> reddens naming
    # both numbers.
    source = (ROOT / "src" / "keelline" / "docs" / "plans.py").read_text(encoding="utf-8")
    codes = {c for c in _PLAN_FINDING_CODE.findall(source)} - {PLAN_REFUSAL_CODE}
    # The floor first: a regex that stopped matching would compare zero against a number word.
    assert len(codes) >= 5, sorted(codes)
    match = _PLAN_RULES_SENTENCE.search(CLI_REFERENCE.read_text(encoding="utf-8"))
    assert match is not None, "docs/cli.md's `plan check` section no longer counts its rules"
    assert _NUMBER_WORDS.get(match.group(1).lower()) == len(codes), (match.group(1), sorted(codes))


# The `doctor` check table: sixteen rows, each spelling a check name, and the one
# code-restating table in this document the branch that built this binding mechanism did not
# bind. `tests/doctor/test_checks.py` pins each name as a literal exactly once *inside*
# `checks.py`, so the document's copy is a sixteenth spelling that guard cannot see and a
# renamed check would leave this page green and wrong. That the unbound ones drift is not a
# hypothesis: `len(OVERLAY_FILES)` is sixteen and four comments one directory over still said
# fourteen.
_DOCTOR_SECTION = re.compile(r"^## `keelline doctor[^\n]*\n(.*?)(?=^## )", re.MULTILINE | re.DOTALL)
# `| `name` | what it answers | what it reads |` — the first cell only, backticked.
_CHECK_ROW = re.compile(r"^\| `([a-z-]+)` \| [^|]+ \| [^|]+ \|$", re.MULTILINE)


def test_the_doctor_table_is_the_registry_and_not_a_second_spelling() -> None:
    # Mutation: rename one check in `docs/cli.md`'s table -> reddens naming the row. In order
    # and not as a set, because the table's order is the report's order and the document says
    # so.
    from keelline.doctor.checks import CHECKS

    section = _DOCTOR_SECTION.search(CLI_REFERENCE.read_text(encoding="utf-8"))
    assert section is not None, "docs/cli.md has no `keelline doctor` section"
    rows = _CHECK_ROW.findall(section.group(1))
    # The walk's floor before anything is compared, for the reason the Shared flags test gives:
    # a regex that matched nothing would make the comparison below vacuously true, and a
    # section that lost its table would look exactly like one that never had it.
    assert len(rows) == len(CHECKS), rows
    expected = [name for name, _ in CHECKS]
    assert rows == expected, [
        (row, name) for row, name in zip(rows, expected, strict=True) if row != name
    ]


# Fix round 1, item 3. The five verdict sentences are `VERDICTS` in
# `keelline.guards.attribute` and are reproduced by hand in `docs/cli.md`'s table; every test
# that had them read the expectation back out of `VERDICTS`, which is shape 9 of the
# `sweep-defect-class` skill's own reference — both sides move together under any reword. This
# is the same rule the Shared flags tables are held to, one section over.
_ATTRIBUTE_SECTION = re.compile(
    r"^## `keelline test attribute[^\n]*\n(.*?)(?=^## )", re.MULTILINE | re.DOTALL
)
# `| fails | passes | — | `sentence` |`: the three code columns, then the sentence in backticks.
_VERDICT_ROW = re.compile(r"^\| (?:fails|passes) \| [^|]+ \| [^|]+ \| `(.+?)` \|$", re.MULTILINE)


def test_the_verdict_table_is_the_shipped_sentences_and_not_a_second_spelling() -> None:
    # Mutation: reword one sentence in `docs/cli.md`'s table — reddens naming the row.
    from keelline.guards.attribute import VERDICTS

    section = _ATTRIBUTE_SECTION.search(CLI_REFERENCE.read_text(encoding="utf-8"))
    assert section is not None, "docs/cli.md has no `keelline test attribute` section"
    rows = _VERDICT_ROW.findall(section.group(1))
    # The walk's floor before anything is compared, for the reason the Shared flags test gives:
    # a regex that matched nothing would make the comparison below vacuously true, and a
    # section that lost its table would look exactly like one that never had it.
    assert len(rows) == len(VERDICTS), rows
    assert tuple(rows) == VERDICTS, [
        (row, sentence) for row, sentence in zip(rows, VERDICTS, strict=True) if row != sentence
    ]
