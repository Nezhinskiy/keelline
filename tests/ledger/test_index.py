"""The index is a pure function of the entry files, and regenerating it must never destroy
content that exists nowhere else.

keelline:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from keelline.config.loader import load
from keelline.config.schema import Config
from keelline.errors import Refusal
from keelline.ledger.check import problems
from keelline.ledger.entries import LedgerError, load_entries
from keelline.ledger.index import (
    GENERATED_BY,
    SECTIONS,
    foreign_index_lines,
    header,
    index_path,
    index_text,
    is_generated_index,
    refuse_index_overwrite,
    render_index,
)

CONFIG = """
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""


def project(tmp_path: Path, extra: str = "") -> tuple[Path, Config]:
    root = tmp_path / "widget"
    root.mkdir()
    (root / "keelline.toml").write_text(CONFIG + extra, encoding="utf-8")
    return root, load(root, machine=tmp_path / "m.toml")


def entry(
    number: int,
    status: str = "open",
    severity: str = "low",
    title: str = "a title",
    fixed_in: str = "",
) -> str:
    fixed = f'fixed_in: "{fixed_in}"' if fixed_in else "fixed_in:"
    if status == "void":
        return (
            f"---\nid: BR-{number:03d}\ntitle: {title}\nstatus: void\n"
            f"found: 2026-01-0{number % 9 + 1}\n---\n\nvoid\n"
        )
    return (
        f"---\nid: BR-{number:03d}\ntitle: {title}\nstatus: {status}\nseverity: {severity}\n"
        f"area: an area\nfound: 2026-01-0{number % 9 + 1}\n"
        f"source:\n{fixed}\nrelated:\n---\n\nbody\n"
    )


def ledger(root: Path, entries: dict[int, str]) -> None:
    bugs = root / "docs" / "bugs"
    bugs.mkdir(parents=True, exist_ok=True)
    for number, text in entries.items():
        (bugs / f"BR-{number:03d}.md").write_text(text, encoding="utf-8")


def test_the_header_is_computed_from_the_configured_paths(tmp_path: Path) -> None:
    _root, config = project(tmp_path)
    assert header(config) == (
        "# Bug reports\n\n"
        f"{GENERATED_BY} from `bugs/BR-*.md`; edit the entry\n"
        "files, not this one. How to file, close, reference, and merge:\n"
        "[runbook](runbooks/bug-reports.md). Audit provenance: "
        "[docs/bugs/audits/](bugs/audits/)._\n"
    )


def test_the_header_follows_a_moved_ledger(tmp_path: Path) -> None:
    # Mutation: hard-code `bugs/` in `header` — this reddens while the test above stays green.
    _root, config = project(
        tmp_path,
        '\n[paths]\nbugs = "ledger/entries"\nbug_index = "ledger/INDEX.md"\nrunbooks = "guides"\n',
    )
    text = header(config)
    assert "from `entries/BR-*.md`" in text
    assert "[runbook](../guides/bug-reports.md)" in text


def test_render_index_groups_by_status_and_counts_each_section(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(
        root,
        {
            1: entry(1),
            2: entry(2, "fixed", fixed_in="`abc1234`"),
            3: entry(3, "void"),
            4: entry(4, "partial", "high"),
        },
    )
    text = render_index(load_entries(root, config), config)
    assert text.startswith(header(config))
    assert (
        "## Open (1)\n\n| ID | Sev | Area | Title | Found |\n|---|---|---|---|---|\n"
        "| [BR-001](bugs/BR-001.md) | low | an area | a title | 2026-01-02 |\n"
    ) in text
    assert "## Partially fixed (1)\n" in text
    assert "## Rejected (0)\n\n| ID | Sev | Area | Title | Found |\n" in text
    assert (
        "## Fixed (1)\n\n| ID | Title | Fixed in |\n|---|---|---|\n"
        "| [BR-002](bugs/BR-002.md) | a title | `abc1234` |\n"
    ) in text
    assert (
        "## Void identifiers (1)\n\n| ID | Why |\n|---|---|\n"
        "| [BR-003](bugs/BR-003.md) | a title |\n"
    ) in text


def test_every_status_has_a_section_to_be_rendered_into() -> None:
    from keelline.ledger.entries import STATUSES

    # Every status the reader accepts has a section to be rendered into, and no section
    # renders a status the reader would reject: a set equality, because the index's reading
    # order is not the reader's vocabulary order and never was.
    assert {status for status, _ in SECTIONS} == set(STATUSES)
    # The reading order is load-bearing (Premise 4: byte-identical regeneration), so it is
    # pinned here as a literal rather than derived from `STATUSES`.
    assert [status for status, _ in SECTIONS] == [
        "open",
        "partial",
        "rejected",
        "fixed",
        "void",
    ]


def test_a_cell_escapes_what_would_break_out_of_its_column(tmp_path: Path) -> None:
    # Backslash first: escaping only the pipe renders `\|` as an escaped backslash and a live
    # separator, and the Found date slides under the wrong heading.
    root, config = project(tmp_path)
    ledger(root, {1: entry(1, title='"a \\\\| b"')})
    rows = [
        line
        for line in render_index(load_entries(root, config), config).splitlines()
        if line.startswith("| [BR-001]")
    ]
    assert rows == ["| [BR-001](bugs/BR-001.md) | low | an area | a \\\\\\| b | 2026-01-02 |"]
    assert rows[0].count("|") - rows[0].count("\\|") == 6


def test_an_empty_ledger_still_renders_every_section_header(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, {})
    text = render_index([], config)
    for _, heading in SECTIONS:
        assert f"## {heading} (0)" in text


def test_a_generated_index_is_recognised_by_its_first_paragraph(tmp_path: Path) -> None:
    _root, config = project(tmp_path)
    assert is_generated_index(render_index([], config))
    # The generator this one replaces wrote a different invocation into the same sentence;
    # adopting the port must not refuse to regenerate over it (Premise 4).
    assert is_generated_index(
        "# Bug reports\n\n_Generated by `python3 a_script.py index` from x._\n"
    )
    assert not is_generated_index("# Bug reports\n\n## BR-001 — a hand-written ledger\n")
    assert not is_generated_index("# Bug reports\n\n_Generated by `something else` from x._\n")


def test_a_reworded_generated_header_is_a_stale_index_not_foreign_content(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    text = render_index([], config).replace(
        "edit the entry\nfiles", "edit the entry files\nand nothing else"
    )
    assert foreign_index_lines(root, text, config) == []


def test_a_paragraph_added_under_the_generated_header_is_still_foreign(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    text = render_index([], config).replace("\n## Open", "\nAn operator's note.\n\n## Open", 1)
    assert foreign_index_lines(root, text, config) == ["An operator's note."]


def test_every_line_the_generator_writes_is_inside_the_grammar_it_enforces(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(
        root,
        {
            1: entry(1),
            2: entry(2, "fixed", fixed_in="`abc`"),
            3: entry(3, "void"),
            4: entry(4, "rejected"),
        },
    )
    assert foreign_index_lines(root, render_index(load_entries(root, config), config), config) == []


@pytest.mark.parametrize(
    "line",
    [
        "##  Open (1)",
        "### Open (1)",
        "## BR-009 — a resurrected section",
        "prose with no identifier",
    ],
)
def test_index_refuses_to_delete_any_content_it_did_not_generate(tmp_path: Path, line: str) -> None:
    # `index` renders from the entry files alone, so anything else in the file is deleted by
    # that write with no diff and exit 0. Mutation: make `foreign_index_lines` return `[]` —
    # every case reddens.
    root, config = project(tmp_path)
    ledger(root, {1: entry(1)})
    current = render_index(load_entries(root, config), config) + f"\n{line}\n"
    with pytest.raises(Refusal, match="did not generate"):
        refuse_index_overwrite(root, config, current)


def test_a_row_whose_entry_file_is_gone_is_foreign_and_not_a_stale_index(tmp_path: Path) -> None:
    # The reproduction: delete one entry file — the shape a merge resolved to the wrong side
    # leaves behind — and its index row is the last record that bug ever existed. Classified by
    # the line's leading `|` it read as tool-generated, so `bugs check` reported
    # `stale-index; run: keelline bugs index` and that command deleted the record, no diff,
    # exit 0. `ENTRIES_MISSING` never fires here: the ledger directory is still there.
    # Mutation: allow any `|` line in `foreign_index_lines` — every assertion reddens.
    root, config = project(tmp_path)
    ledger(root, {1: entry(1), 2: entry(2, title="the only record of this bug")})
    current = render_index(load_entries(root, config), config)
    (root / "docs" / "bug-reports.md").write_text(current, encoding="utf-8")
    (root / "docs" / "bugs" / "BR-002.md").unlink()
    foreign = foreign_index_lines(root, current, config)
    assert len(foreign) == 1 and "the only record of this bug" in foreign[0]
    with pytest.raises(Refusal, match="recover it before regenerating"):
        refuse_index_overwrite(root, config, current)
    rules = [f.rule for f in problems(root, config)]
    assert "foreign-index-content" in rules and "stale-index" not in rules


def test_an_injected_section_of_hand_written_rows_is_foreign(tmp_path: Path) -> None:
    # A whole `## Open (99)` section of rows nobody generated was classified clean for the same
    # reason: every one of its lines opens with `|`. Mutation: allow any `|` line — this reddens.
    root, config = project(tmp_path)
    ledger(root, {1: entry(1)})
    injected = (
        "| [BR-900](bugs/BR-900.md) | high | area | filed by hand | 2026-02-02 |\n"
        "| [BR-901](bugs/BR-901.md) | high | area | and another | 2026-02-02 |\n"
    )
    current = render_index(load_entries(root, config), config).replace(
        "\n## Partially fixed", f"{injected}\n## Partially fixed", 1
    )
    assert len(foreign_index_lines(root, current, config)) == 2
    with pytest.raises(Refusal, match="recover it before regenerating"):
        refuse_index_overwrite(root, config, current)


def test_a_generated_index_whose_entry_files_are_gone_is_refused(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, {1: entry(1)})
    current = render_index(load_entries(root, config), config)
    shutil.rmtree(root / "docs" / "bugs")
    with pytest.raises(Refusal, match="restore them rather than regenerating"):
        refuse_index_overwrite(root, config, current)


def test_a_stale_but_generated_index_is_not_refused(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, {1: entry(1)})
    stale = render_index([], config)
    refuse_index_overwrite(root, config, stale)  # no raise: the remedy is regeneration
    assert index_path(root, config) == root / "docs" / "bug-reports.md"


def test_an_index_that_cannot_be_decoded_is_a_ledger_error_not_an_empty_index(
    tmp_path: Path,
) -> None:
    # Answering `""` for an index that exists but cannot be read would say the ledger is
    # uninitialised and pass the check over a tree nobody has looked at.
    root, config = project(tmp_path)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "bug-reports.md").write_bytes(b"# Bug reports\n\n\xff\n")
    with pytest.raises(LedgerError, match="is not valid UTF-8"):
        index_text(root, config)


def test_load_entries_reports_an_undecodable_entry_as_a_ledger_error(tmp_path: Path) -> None:
    # Wave A2's writing commands call `load_entries`; a bare `UnicodeDecodeError` out of it
    # would reach the frame as an internal error rather than as findings.
    root, config = project(tmp_path)
    ledger(root, {1: entry(1)})
    (root / "docs" / "bugs" / "BR-002.md").write_bytes(b"---\nid: BR-002\ntitle: \xff\n---\n")
    with pytest.raises(LedgerError, match="is not valid UTF-8"):
        load_entries(root, config)
