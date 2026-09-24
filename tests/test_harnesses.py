"""The harness registry, and the one profile rendering this wave ships."""

from __future__ import annotations

from keelline.harnesses import CLAUDE, CODEX, HARNESSES, select
from keelline.profiles import load_profile


def test_the_claude_rule_is_path_scoped_and_points_at_the_one_copy() -> None:
    profile = load_profile("python")
    assert CLAUDE.render_profile is not None
    rendition = CLAUDE.render_profile(profile, "docs/keelline/rules/python.md")
    assert rendition.artifact_id == "claude-rules"
    # `keelline-` says who owns the file and leaves `python.md` to the project.
    assert rendition.target == ".claude/rules/keelline-python.md"
    head, _, body = rendition.render().partition("---\n\n")
    assert head.startswith("---\npaths:\n")
    for glob in profile.scope:
        assert f'  - "{glob}"\n' in head
    # A pointer, not a copy: nothing of the rules' prose is in the file, so an edit to the one
    # copy is what every session reads. Mutation: render `head + profile.rules` instead of the
    # pointer -> the next two assertions redden.
    assert "`docs/keelline/rules/python.md`" in body
    assert profile.essentials[0] not in body and len(body.splitlines()) == 1


def test_select_answers_the_listed_harnesses_and_counts_the_rest() -> None:
    assert select(["claude", "codex"]) == ((CLAUDE, CODEX), 0)
    assert select(["codex"]) == ((CODEX,), 0)
    assert select(["claude", "cursor", "x\x1b"]) == ((CLAUDE,), 2)


def test_every_harness_is_registered_once_and_codex_reads_only_the_standard() -> None:
    names = [harness.name for harness in HARNESSES]
    assert len(names) == len(set(names))
    # Codex reads `AGENTS.md` and no other instruction file, so it has no rendering of its own
    # and is served by the region alone.
    assert CODEX.render_profile is None
    assert CLAUDE.settings == (".claude/settings.json",)
    assert CODEX.settings == (".codex/hooks.json",)
    # `project.detect` reads these instead of spelling the directories a second time.
    assert (CLAUDE.marker_dir, CODEX.marker_dir) == (".claude", ".codex")
