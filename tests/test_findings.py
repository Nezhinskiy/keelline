from __future__ import annotations

from keelline.findings import LISTED_LIMIT, Finding, labels, listed


def test_a_label_is_the_path_the_line_and_the_rule_and_never_the_detail() -> None:
    # The summary line carries labels; `detail` may quote the repository and stays in `--json`.
    assert Finding("dead-link", "docs/a.md", 12, "quoted text").label == "docs/a.md:12 [dead-link]"
    assert (
        Finding("stale-index", "docs/bug-reports.md", None, "x").label
        == "docs/bug-reports.md [stale-index]"
    )
    assert Finding("base-unresolvable", "", None, "x").label == "- [base-unresolvable]"


def test_listed_caps_the_tail_and_says_how_many_it_dropped() -> None:
    # An unmigrated ledger had 134 identifiers and the remediation was one command for the
    # whole set; the tail is length, not information. Mutation: drop the cap — the first
    # assertion reddens.
    items = [f"item-{n}" for n in range(LISTED_LIMIT + 3)]
    assert listed(items).endswith(", and 3 more")
    assert listed(items[:LISTED_LIMIT]).count(",") == LISTED_LIMIT - 1
    assert listed([]) == ""


def test_labels_renders_findings_through_the_same_cap() -> None:
    findings = [Finding("r", f"p{n}.md", n, "d") for n in range(LISTED_LIMIT + 1)]
    assert labels(findings).startswith("p0.md:0 [r], ") and labels(findings).endswith(
        ", and 1 more"
    )
