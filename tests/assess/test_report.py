"""What a gate run hands a person: printed lines, the platform's workflow commands, a job summary.

Every string here can reach a pull request's annotations or its job summary, which a reviewer
reads as Keelline's own words. So each case holds one of two things: a repository-authored
string (a finding's path outside the grammar a path may print in, a finding's detail) never
reaches them, or the platform's bound (ten annotations per level per step, the rest dropped
without a word) is counted rather than met silently.
"""

from __future__ import annotations

from collections.abc import Iterable

from keelline.assess.gates import GateResult
from keelline.assess.report import GateRun, summary, workflow_commands
from keelline.assess.rule import Change, ConfigVerdict, Verdict
from keelline.config.loader import preset_defaults
from keelline.findings import Finding


def _run(
    results: Iterable[GateResult],
    enforcing: Iterable[str],
    changes: Iterable[Change] = (),
    prefix: str = "",
    judged: bool = True,
) -> GateRun:
    verdict = ConfigVerdict(
        "adopting", tuple(changes), preset_defaults("widget"), frozenset(enforcing)
    )
    return GateRun(verdict, tuple(results), judged=judged, prefix=prefix)


def _link(path: str, line: int | None = 1, detail: str = "a link to nowhere") -> Finding:
    return Finding("missing-link", path, line, detail)


def _level(command: str) -> str:
    """`error`, `warning` or `notice`: the word after the leading `::`."""
    return command.removeprefix("::").split("::")[0].split(" ")[0]


def test_a_path_outside_the_printable_grammar_is_annotated_without_a_location() -> None:
    # A committed file's name is anything a contributor chose: a newline and `::error::` in it
    # would forge an annotation of its own, and a space is merely outside the grammar. Both are
    # still annotated, at no location.
    run = _run(
        [GateResult("docs", (_link("a\n::error::forged:b,c%d", 3), _link("docs/My Notes.md")))],
        ["docs"],
    )
    assert workflow_commands(run) == ["::error::docs: missing-link", "::error::docs: missing-link"]


def test_an_advisory_gate_warns_and_an_enforcing_one_errors() -> None:
    run = _run(
        [GateResult("bugs", (_link(""),)), GateResult("docs", (_link(""),))],
        ["docs"],
    )
    assert [_level(line) for line in workflow_commands(run)] == ["warning", "error"]


def test_past_the_cap_one_notice_counts_the_rest() -> None:
    # The platform shows ten annotations per level per step and drops the rest without a word,
    # so a reader who counts eleven lines would think eleven was all.
    run = _run([GateResult("docs", tuple(_link("") for _ in range(13)))], ["docs"])
    lines = workflow_commands(run, cap=10)
    assert len(lines) == 11
    assert lines[-1] == (
        "::notice::3 more error annotation(s) not shown; the job summary counts them all"
    )


def test_refusals_share_the_cap_with_findings() -> None:
    changes = [Change(f"paths.k{n:02}", Verdict.REFUSED) for n in range(12)]
    lines = workflow_commands(_run([], [], changes), cap=10)
    assert [_level(line) for line in lines[:-1]] == ["error"] * 10
    assert lines[-1].startswith("::notice::2 more error annotation(s)")


def test_a_path_is_written_from_the_repository_s_root() -> None:
    # The platform places an annotation by the repository's path, and a project kept in a
    # subdirectory reports paths from its own root.
    run = _run(
        [GateResult("docs", (_link("AGENTS.md", 2),))],
        ["docs"],
        [Change("paths.bugs", Verdict.REFUSED)],
        prefix="sub/",
    )
    assert workflow_commands(run) == [
        "::error file=sub/keelline.toml::paths.bugs may not change this way in a pull request",
        "::error file=sub/AGENTS.md,line=2::docs: missing-link",
    ]


def test_a_commit_finding_is_annotated_without_a_file() -> None:
    # A `commit` finding's path is the commit's id, which is inside the grammar. `located_here =
    # True` would annotate a file named after it: a misplaced annotation, not a trust decision,
    # so it is not declared as a mutation.
    run = _run([GateResult("commit", (Finding("attribution", "d" * 40, None, "x"),))], ["commit"])
    assert workflow_commands(run) == ["::error::commit: attribution"]


def test_the_summary_and_the_commands_carry_counts_and_rules_never_a_path_s_detail() -> None:
    detail = "a-detail-we-wrote"
    run = _run(
        [GateResult("docs", (_link("private/path.md", 1, detail),))],
        ["docs"],
        [Change("paths.bugs", Verdict.REFUSED)],
    )
    text = summary(run)
    assert "| docs | enforcing | 1 | fails |" in text
    assert "| paths.bugs | refused |" in text
    assert "private/path.md" not in text
    assert detail not in text
    assert text.endswith("\n")
    assert not [line for line in workflow_commands(run) if detail in line]


def test_the_summary_says_how_the_configuration_was_judged() -> None:
    # Advice, not declared: each branch is fixed text. Mutation: drop the `base_state is None`
    # branch -> the bootstrap reads as "unchanged from the base" and the first assertion reddens.
    bootstrap = GateRun(
        ConfigVerdict(None, (), preset_defaults("widget"), frozenset()), (), judged=True
    )
    assert "the base has none at this path, so this tree's decides" in summary(bootstrap)
    assert "keelline.toml: unchanged from the base" in summary(_run([], []))
    unanswered = GateResult("tests", (), answered=False, reason="could not start")
    advisory = _run([unanswered, GateResult("bugs", (_link(""),))], [], judged=False)
    text = summary(advisory)
    assert "| tests | advisory | could not run | would fail |" in text
    assert "| bugs | advisory | 1 | would fail |" in text
    assert "keelline.toml" not in text


def test_the_exit_code_counts_only_what_enforces_and_what_the_rule_refused() -> None:
    finding = GateResult("docs", (_link(""),))
    refused = [Change("paths.bugs", Verdict.REFUSED)]
    assert _run([finding], []).exit_code == 0
    assert _run([finding], ["docs"]).exit_code == 1
    assert _run([], [], refused).exit_code == 1
    assert _run([], [], refused, judged=False).exit_code == 0
    assert _run([GateResult("docs", ())], ["docs"], [Change("x", Verdict.NOTED)]).exit_code == 0
