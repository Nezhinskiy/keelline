"""Every rule `bugs check` reports, one fixture each.

keelline:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

from pathlib import Path

from keelline.config.loader import load
from keelline.config.schema import Config
from keelline.ledger.check import EVIDENCE_LABEL, EVIDENCE_PLACEHOLDER, problems, uninitialised
from keelline.ledger.entries import load_entries
from keelline.ledger.index import render_index

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
    for name in ("src", "tests", "scripts", "docs"):
        (root / name).mkdir()
    return root, load(root, machine=tmp_path / "m.toml")


def entry(number: int, *, severity: str = "low", body: str = "body\n", related: str = "") -> str:
    return (
        f"---\nid: BR-{number:03d}\ntitle: a title\nstatus: open\nseverity: {severity}\n"
        f"area: an area\nfound: 2026-01-01\nsource:\nfixed_in:\nrelated: {related}\n---\n\n{body}"
    )


def ledger(root: Path, config: Config, entries: dict[str, str]) -> None:
    bugs = root / "docs" / "bugs"
    bugs.mkdir(parents=True, exist_ok=True)
    for name, text in entries.items():
        (bugs / f"{name}.md").write_text(text, encoding="utf-8")
    (root / "docs" / "bug-reports.md").write_text(
        render_index(load_entries(root, config), config), encoding="utf-8"
    )


def rules(root: Path, config: Config) -> list[str]:
    return [problem.rule for problem in problems(root, config)]


def test_check_is_inert_before_a_ledger_exists(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    assert uninitialised(root, config)
    assert problems(root, config) == []


def test_a_generated_index_with_no_entries_directory_is_a_deleted_ledger(tmp_path: Path) -> None:
    # Mutation: drop the `is_generated_index` conjunct from `uninitialised` — this reddens.
    root, config = project(tmp_path)
    (root / "docs" / "bug-reports.md").write_text(render_index([], config), encoding="utf-8")
    assert not uninitialised(root, config)
    assert rules(root, config) == ["entries-missing"]


def test_check_accepts_a_clean_ledger(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1)})
    assert problems(root, config) == []


def test_a_conflict_marker_is_reported_before_the_entry_is_parsed(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1)})
    (root / "docs" / "bugs" / "BR-001.md").write_text(
        "<<<<<<< ours\n" + entry(1) + "=======\n>>>>>>> theirs\n", encoding="utf-8"
    )
    found = problems(root, config)
    assert [p.rule for p in found] == ["conflict-marker", "stale-index"]
    assert found[0].path == "docs/bugs/BR-001.md"


def test_an_id_that_disagrees_with_its_filename_is_reported(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-002": entry(1)})
    assert "id-mismatch" in rules(root, config)


def test_a_body_that_restates_status_or_severity_is_reported(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1, body="- **Status:** open\n")})
    assert rules(root, config) == ["state-in-body"]


def test_two_files_claiming_one_identifier_are_reported_once(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1), "BR-002": entry(1)})
    found = [p for p in problems(root, config) if p.rule == "duplicate-id"]
    assert len(found) == 1 and "BR-002.md" in found[0].detail


def test_a_related_identifier_with_no_entry_is_reported(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1, related="[BR-009]")})
    assert rules(root, config) == ["dangling-related"]


def test_high_severity_needs_a_filled_evidence_boundary(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1, severity="high")})
    assert rules(root, config) == ["evidence-boundary"]


def test_the_untouched_scaffold_placeholder_does_not_satisfy_the_rule(tmp_path: Path) -> None:
    # A placeholder that satisfies its own check is the failure mode the rule exists to
    # prevent. Mutation: drop the negative lookahead — this reddens.
    root, config = project(tmp_path)
    ledger(
        root,
        config,
        {
            "BR-001": entry(
                1,
                severity="high",
                body=f"{EVIDENCE_LABEL} {EVIDENCE_PLACEHOLDER} —\nname what.\n",
            )
        },
    )
    assert rules(root, config) == ["evidence-boundary"]


def test_a_filled_evidence_boundary_passes(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(
        root,
        config,
        {
            "BR-001": entry(
                1,
                severity="high",
                body=f"{EVIDENCE_LABEL} whether the read path is reached at all.\n",
            )
        },
    )
    assert problems(root, config) == []


def test_an_empty_boundary_line_is_not_rescued_by_later_body_text(tmp_path: Path) -> None:
    # `[^\S\n]*` and not `\s*`: the latter crosses newlines under MULTILINE. Mutation: replace
    # it with `\s*` — this reddens.
    root, config = project(tmp_path)
    ledger(
        root,
        config,
        {"BR-001": entry(1, severity="high", body=f"{EVIDENCE_LABEL}\n\nlater prose\n")},
    )
    assert rules(root, config) == ["evidence-boundary"]


def test_the_severities_that_need_a_boundary_come_from_configuration(tmp_path: Path) -> None:
    root, config = project(
        tmp_path, '\n[ledger]\nevidence_boundary_required_for = ["high", "medium"]\n'
    )
    ledger(root, config, {"BR-001": entry(1, severity="medium")})
    assert rules(root, config) == ["evidence-boundary"]


def test_foreign_index_content_is_reported_and_staleness_is_not_named_beside_it(
    tmp_path: Path,
) -> None:
    # Regenerating is what deletes the content, so the stale row must not recommend it.
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1)})
    index = root / "docs" / "bug-reports.md"
    index.write_text(
        index.read_text(encoding="utf-8") + "\nAn operator's note.\n", encoding="utf-8"
    )
    (root / "docs" / "bugs" / "BR-002.md").write_text(entry(2), encoding="utf-8")
    assert rules(root, config) == ["foreign-index-content"]


def test_a_stale_index_is_reported_with_the_command_that_repairs_it(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1)})
    (root / "docs" / "bugs" / "BR-002.md").write_text(entry(2), encoding="utf-8")
    found = problems(root, config)
    assert [p.rule for p in found] == ["stale-index"]
    assert "keelline bugs index" in found[0].detail


def test_a_mention_with_no_entry_is_reported_at_its_first_location(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1)})
    (root / "src" / "b.py").write_text("# BR-404\n", encoding="utf-8")
    (root / "src" / "a.py").write_text("x = 1\n# BR-404 again\n", encoding="utf-8")
    found = problems(root, config)
    assert [(p.rule, p.path, p.line) for p in found] == [("dangling-mention", "src/a.py", 2)]
    assert "referenced 2 time(s)" in found[0].detail


def test_a_void_entry_keeps_its_number_resolvable(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    void = "---\nid: BR-001\ntitle: renumbered\nstatus: void\nfound: 2026-01-01\n---\n\nvoid\n"
    ledger(root, config, {"BR-001": void})
    (root / "src" / "a.py").write_text("# BR-001\n", encoding="utf-8")
    assert problems(root, config) == []


def test_a_citation_of_an_unfiled_entry_is_reported_from_a_document(tmp_path: Path) -> None:
    # Wider than the mention scan: it reads documents, because renaming an entry file leaves
    # the stale link in a docs-only commit.
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1)})
    (root / "docs" / "roadmap.md").write_text("see [x](bugs/BR-404.md)\n", encoding="utf-8")
    found = problems(root, config)
    assert [(p.rule, p.path, p.line) for p in found] == [
        ("dangling-citation", "docs/roadmap.md", 1)
    ]


def test_a_worked_example_in_a_document_is_not_a_dangling_mention(tmp_path: Path) -> None:
    # Documents are outside the mention roots on purpose (plan documents spell invented
    # identifiers as worked examples of this very guard).
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1)})
    (root / "docs" / "plan.md").write_text("imagine BR-404 here\n", encoding="utf-8")
    assert problems(root, config) == []


def test_every_problem_names_a_repo_relative_path(tmp_path: Path) -> None:
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1, related="[BR-009]")})
    (root / "docs" / "bugs" / "BR-002.md").write_text("no frontmatter\n", encoding="utf-8")
    for problem in problems(root, config):
        assert not problem.path.startswith("/"), problem
    labels = [p.label for p in problems(root, config)]
    assert "docs/bugs/BR-002.md [unreadable-entry]" in labels
