from __future__ import annotations

from keelline.findings import LISTED_LIMIT, UNPRINTABLE, Finding, labels, listed


def test_a_label_is_the_path_the_line_and_the_rule_and_never_the_detail() -> None:
    # The summary line carries labels; `detail` may quote the repository and stays in `--json`.
    assert Finding("dead-link", "docs/a.md", 12, "quoted text").label == "docs/a.md:12 [dead-link]"
    assert (
        Finding("stale-index", "docs/bug-reports.md", None, "x").label
        == "docs/bug-reports.md [stale-index]"
    )
    assert Finding("base-unresolvable", "", None, "x").label == "- [base-unresolvable]"


def test_listed_caps_the_tail_and_says_how_many_it_dropped() -> None:
    # A check over a neglected ledger reports findings by the hundred and the remediation is one
    # command for the whole set; the tail is length, not information, and printing it pushes that
    # command off the end of the line. Mutation: drop the cap — the first assertion reddens.
    items = [f"item-{n}" for n in range(LISTED_LIMIT + 3)]
    assert listed(items).endswith(", and 3 more")
    assert listed(items[:LISTED_LIMIT]).count(",") == LISTED_LIMIT - 1
    assert listed([]) == ""


def test_labels_renders_findings_through_the_same_cap() -> None:
    findings = [Finding("r", f"p{n}.md", n, "d") for n in range(LISTED_LIMIT + 1)]
    assert labels(findings).startswith("p0.md:0 [r], ") and labels(findings).endswith(
        ", and 1 more"
    )


# A name a repository can commit: a line break, a line the Actions runner reads as a workflow
# command, and a terminal escape that clears the screen.
CRAFTED = "docs/x\n::error::forged\x1b[2J.md"


def test_a_path_outside_the_grammar_never_reaches_a_label_raw() -> None:
    # The label is printed on stdout by `bugs check`, `docs check`, `plan check` and
    # `memory refs`, and in CI a line that starts `::error::` is an instruction to the runner.
    # Mutation: return the path unchecked from `printable`, or print `self.path` in `label` —
    # either reddens.
    label = Finding("dead-link", CRAFTED, 3, "d").label
    assert "\n" not in label and "\x1b" not in label and "::error::" not in label
    assert label == f"{UNPRINTABLE}:3 [dead-link]"
    assert labels([Finding("dead-link", CRAFTED, None, "d")]) == f"{UNPRINTABLE} [dead-link]"
