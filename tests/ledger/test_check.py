"""Every rule `bugs check` reports, one fixture each.

keelline:ledger:fixtures — the identifiers below are sample data, not claims about a ledger.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from keelline.config.loader import load
from keelline.config.schema import Config
from keelline.errors import Failure, Refusal
from keelline.ledger.check import EVIDENCE_LABEL, EVIDENCE_PLACEHOLDER, problems, uninitialised
from keelline.ledger.entries import load_entries
from keelline.ledger.index import render_index
from tests.gitfixture import git, needs_git

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


def test_with_no_ledger_every_citation_of_an_entry_file_dangles(tmp_path: Path) -> None:
    # "No ledger yet" is read off the tree, and a pull request writes the tree: deleting the
    # ledger and its index must not switch an enforced gate off while code still cites entry
    # files. A project that registers the gate before its first entry cites none, and the case
    # above holds that it stays green. Mutation (declared): the uninitialised arm answers `[]`
    # again -> nothing is reported.
    root, config = project(tmp_path)
    (root / "src" / "a.py").write_text("# see docs/bugs/BR-001.md\n", encoding="utf-8")
    (root / "docs" / "roadmap.md").write_text("see [x](bugs/BR-404.md)\n", encoding="utf-8")
    assert uninitialised(root, config)
    found = problems(root, config)
    # The code's citation names the identifier too, so it is a mention as well, as it is once a
    # ledger exists; the roadmap is outside the trees swept for mentions.
    assert [(p.rule, p.path, p.line) for p in found] == [
        ("dangling-mention", "src/a.py", 1),
        ("dangling-citation", "src/a.py", 1),
        ("dangling-citation", "docs/roadmap.md", 1),
    ]


def test_with_no_ledger_a_bare_mention_dangles_too(tmp_path: Path) -> None:
    # A bare identifier is the ordinary way code refers to a bug, so with the ledger deleted a
    # `# workaround for BR-001` is as dangling as a citation of its file: reported only for
    # citations, deleting the ledger and its index switched an enforced gate off for every
    # mention. Mutation (oracle): "with no ledger a bare mention is not a finding" -> nothing is
    # reported.
    root, config = project(tmp_path)
    (root / "src" / "a.py").write_text("# workaround for BR-001\n", encoding="utf-8")
    assert [(p.rule, p.path, p.line) for p in problems(root, config)] == [
        ("dangling-mention", "src/a.py", 1)
    ]


def _based(tmp_path: Path, on_base: str) -> tuple[Path, Config, str]:
    """A project whose one commit carries `on_base` of the ledger (`both`, `directory`, `index`
    or `none`), with the tree then emptied of it; the commit's id is the base."""
    root, config = project(tmp_path)
    git(root, "init", "-q", "-b", "main")
    if on_base in ("both", "directory"):
        ledger(root, config, {"BR-001": entry(1)})
    if on_base == "directory":
        (root / "docs" / "bug-reports.md").unlink()
    if on_base == "index":
        (root / "docs" / "bug-reports.md").write_text(render_index([], config), encoding="utf-8")
    (root / "README.md").write_text("widget\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    base = git(root, "rev-parse", "HEAD").strip()
    shutil.rmtree(root / "docs" / "bugs", ignore_errors=True)
    (root / "docs" / "bug-reports.md").unlink(missing_ok=True)
    return root, config, base


@needs_git
@pytest.mark.parametrize("on_base", ["both", "directory", "index"])
def test_a_tree_that_deleted_the_base_s_ledger_is_one_ledger_removed_finding(
    tmp_path: Path, on_base: str
) -> None:
    # "No ledger" is read off the tree, which the change wrote, so the base is asked whether it
    # had one: deleting the ledger, the index and every mention together passed, with nothing
    # left in the tree to dangle. Mutation (oracle): "the uninitialised arm ignores the base's
    # ledger" -> nothing is reported.
    root, config, base = _based(tmp_path, on_base)
    assert uninitialised(root, config)
    assert [(p.rule, p.path) for p in problems(root, config, base)] == [
        ("ledger-removed", "docs/bugs")
    ]
    # Without a base the tree alone is judged, as `bugs check` without `--base` judges it.
    assert problems(root, config) == []
    # And a mention still dangles beside it: both are the change's to answer for.
    (root / "src" / "a.py").write_text("# workaround for BR-001\n", encoding="utf-8")
    assert [p.rule for p in problems(root, config, base)] == ["ledger-removed", "dangling-mention"]


@needs_git
def test_a_base_with_no_ledger_leaves_a_project_before_its_first_entry_green(
    tmp_path: Path,
) -> None:
    # The gate can be enforced before the first entry: no ledger on the base and no reference
    # in the tree is nothing to report.
    root, config, base = _based(tmp_path, "none")
    assert problems(root, config, base) == []


@needs_git
def test_a_base_git_cannot_list_never_reads_as_a_base_with_no_ledger(tmp_path: Path) -> None:
    # A base this clone does not have is a question with no answer, and "the base had no
    # ledger" would pass exactly the change the question exists to catch: a `Failure`, which a
    # gate run reports as could not run. Mutation (oracle): "a base git cannot list reads as a
    # base with no ledger" -> `problems` returns `[]`.
    root, config, _base = _based(tmp_path, "both")
    with pytest.raises(Failure) as caught:
        problems(root, config, "refs/remotes/origin/main")
    assert "proved nothing" in str(caught.value)
    # Shaped like an option, it is refused before git sees it, as `plan check` refuses it.
    with pytest.raises(Refusal):
        problems(root, config, "--output=x")


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


def test_an_entry_that_is_not_utf8_is_reported_rather_than_crashing_the_check(
    tmp_path: Path,
) -> None:
    # The `unreadable-entry` rule exists for exactly this file, and an unguarded read meant it
    # could never fire from the one path that reaches it: the `UnicodeDecodeError` escaped
    # `problems()` and `cli.run` turned a fixable repository condition into exit 2.
    root, config = project(tmp_path)
    ledger(root, config, {"BR-001": entry(1)})
    (root / "docs" / "bugs" / "BR-002.md").write_bytes(b"---\nid: BR-002\ntitle: \xff\n---\n")
    found = problems(root, config)
    assert "docs/bugs/BR-002.md [unreadable-entry]" in [p.label for p in found]
    unreadable = next(p for p in found if p.rule == "unreadable-entry")
    assert "is not valid UTF-8" in unreadable.detail
