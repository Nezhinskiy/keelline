"""Skills are documents held to a contract: frontmatter, a line budget, action language, and
invocations that parse against the real parser or are allow-listed by the package that will
ship them (§5.5, Premise 13 and 14)."""

from __future__ import annotations

import io
import re
import shlex
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, split_json_flag

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"
# The plugin's own skill_lines lint (§5.1): a SKILL.md is an entry point, and detail belongs in
# `references/`. Not a config key — it bounds a file this repository ships, not a project's.
SKILL_MAX_LINES = 80
# Harness tool names a skill body may not use (§5.5: "action language, never tool names").
# The per-harness mapping lives in skills/README.md and is held to this same list.
TOOL_NAMES = (
    "Read",
    "Grep",
    "Glob",
    "Bash",
    "Edit",
    "Write",
    "WebFetch",
    "WebSearch",
    "AskUserQuestion",
    "Agent",
    "LSP",
    "NotebookEdit",
    "TodoWrite",
)
_TOOL = re.compile(r"\b(?:" + "|".join(TOOL_NAMES) + r")\b")
# Commands the wrapper skills describe against C5 before the command exists, keyed to the
# package that ships each (§15.2). The lane that ships one DELETES its entry: a parsing
# command that is still listed here reddens `test_every_invocation_parses_or_is_allowlisted`.
NOT_YET_SHIPPED = {
    "init": "onboarding",
    "upgrade": "upgrade",
    "uninstall": "upgrade",
    "attach": "attach",
    "detach": "attach",
    "setup": "setup",
    "doctor": "hooks-core",
}
PACKAGES = {"onboarding", "upgrade", "attach", "setup", "hooks-core"}
_INVOCATION = re.compile(r"`keelline ([^`\n]+)`")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


def skills() -> list[Path]:
    return sorted(SKILLS.glob("*/SKILL.md"))


def split(path: Path) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
    assert match is not None, f"{path} has no frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields, match.group(2)


def test_the_walk_finds_the_ported_skills() -> None:
    # The mutation guard for the parametrised tests below: an empty `skills/` passes them all.
    names = {path.parent.name for path in skills()}
    assert {"close-bug", "memory-sweep"} <= names


@pytest.mark.parametrize("path", skills(), ids=lambda p: p.parent.name)
def test_every_skill_has_a_name_matching_its_directory_and_a_description(path: Path) -> None:
    fields, _ = split(path)
    assert fields["name"] == path.parent.name
    assert len(fields["description"]) > 40, "a description is what the harness matches on"


@pytest.mark.parametrize("path", skills(), ids=lambda p: p.parent.name)
def test_every_skill_stays_within_the_line_budget(path: Path) -> None:
    assert len(path.read_text(encoding="utf-8").splitlines()) <= SKILL_MAX_LINES


@pytest.mark.parametrize("path", skills(), ids=lambda p: p.parent.name)
def test_no_skill_body_names_a_harness_tool(path: Path) -> None:
    # Mutation: write "use the Grep tool" into a skill body — that skill's case reddens.
    _, body = split(path)
    assert _TOOL.search(body) is None, _TOOL.search(body)


@pytest.mark.parametrize("path", skills(), ids=lambda p: p.parent.name)
def test_every_invocation_parses_or_is_allowlisted(path: Path) -> None:
    parser = build_parser(discover_registrars())
    _, body = split(path)
    invocations = _INVOCATION.findall(body)
    assert invocations, "a skill that names no command is not a wrapper"
    for invocation in invocations:
        argv, _ = split_json_flag(shlex.split(invocation))
        with redirect_stderr(io.StringIO()):
            try:
                parser.parse_args(argv)
                parsed = True
            except SystemExit:
                parsed = False
        if argv[0] in NOT_YET_SHIPPED:
            assert not parsed, (
                f"`keelline {invocation}` parses now; delete its NOT_YET_SHIPPED entry "
                f"({NOT_YET_SHIPPED[argv[0]]} shipped it)"
            )
        else:
            assert parsed, f"`keelline {invocation}` does not parse against the real parser"


def test_the_allowlist_names_only_packages_the_design_defines() -> None:
    assert set(NOT_YET_SHIPPED.values()) <= PACKAGES


def test_the_readme_maps_every_tool_name_for_both_harnesses() -> None:
    text = (SKILLS / "README.md").read_text(encoding="utf-8")
    for name in TOOL_NAMES:
        assert f"`{name}`" in text, name
    assert "Codex" in text and "Claude Code" in text


@pytest.mark.parametrize("path", skills(), ids=lambda p: p.parent.name)
def test_every_reference_file_is_linked_from_its_skill(path: Path) -> None:
    body = path.read_text(encoding="utf-8")
    for reference in sorted((path.parent / "references").glob("*.md")):
        assert f"references/{reference.name}" in body, reference
