"""§5.8: no project-identifying string in the public repository, held over this lane's files.

The design's whole-tree gate belongs to the `workflows` lane; this is the same rule scoped to
what the `guards` port can carry in, checked from the first task so a ported docstring cannot
land the state §11 requires it to shed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LANE = (ROOT / "src" / "keelline" / "guards", ROOT / "tests" / "guards")

# Lower-cased substrings. Each is a path, identifier or name that belongs to the repository the
# guards were extracted from and to no other; none is a word a neutral guard needs.
FORBIDDEN = (
    "daybook",
    "infra/",
    "env_access_guard",
    "eval_scope",
    "local_ci_checks",
    "bug_ledger_memory_hook",
    "install_git_hooks",
    "app-env-value",
    "app.demo",
    "docs/superpowers",
    "docs/memory",
    "docs/runbooks",
    "docs/architecture",
    "frontend/",
    "ci-cd.yml",
    "graphify",
    "temporal",
    "br-1",
    "pr #",
    "showcase",
)
# Shapes a substring list cannot express: a personal address, a bare commit id, a
# vendor-prefixed branch name. Each arm is named so a hit says what it is.
SHAPES = (
    # Not `@users.noreply.github.com`: that is GitHub's generic form and a Task 5 negative.
    ("personal email", re.compile(r"@(?:gmail|yandex|mail|icloud|proton)\.\w+")),
    # At least one digit, so an eight-letter hex word (`deadbeef`) is not an id.
    ("bare commit id", re.compile(r"(?<![\w/])(?=[0-9a-f]*\d)[0-9a-f]{8,10}(?![\w/])")),
    ("vendor branch", re.compile(r"\b(?:codex|claude|cursor)/[a-z0-9][\w-]*")),
)


def offending(text: str) -> list[str]:
    lowered = text.lower()
    found = [token for token in FORBIDDEN if token in lowered]
    found.extend(name for name, shape in SHAPES if shape.search(lowered))
    return found


def lane_files() -> list[Path]:
    found = [path for directory in LANE for path in directory.rglob("*.py")]
    # The lane's non-Python artifacts are gated too; the whole-tree gate is `workflows`'.
    # `docs/cli.md` is deliberately not walked here: it is a shared, pre-existing file written
    # by other lanes, not this lane's ported state — `docs/cli.md:165` has `memory =
    # "docs/memory"` (hits FORBIDDEN `docs/memory`) and `:192` has `.claude/settings.json`
    # (hits the `vendor branch` regex), both Keelline's own strings. Its guards sections are
    # checked by hand at Task 10.
    extra = "changelog.d/guards.feature.md"
    if (ROOT / extra).is_file():
        found.append(ROOT / extra)
    # This file names every token on purpose; it is the one file the gate does not read.
    return sorted(path for path in found if path.name != "test_neutral.py")


def test_the_gate_reads_something() -> None:
    # No mutation of its own: this is the mutation guard for the test below, which passes
    # vacuously if the walk ever finds no files.
    assert any(path.name == "__init__.py" for path in lane_files())


def test_the_gate_discriminates() -> None:
    # The oracle for the gate itself: a token planted in a synthetic string is found, and so
    # is each regex arm; a neutral fixture is not.
    assert offending("see Docs/Superpowers/plans") == ["docs/superpowers"]
    assert offending("Co-authored-by: Someone <someone@gmail.com>") == ["personal email"]
    assert offending("fixed in 1b279648") == ["bare commit id"]
    assert offending("cut from codex/inbound-remediation") == ["vendor branch"]
    assert offending("cat secrets/.env; person@example.com; 0x1234; deadbeef") == []
    assert offending("Co-authored-by: Someone <someone@users.noreply.github.com>") == []


def test_mutations_toml_carries_no_source_repository_string() -> None:
    # `mutations.toml` is a shared file, so only this lane's entries are read: the ones whose
    # `file` names the guards package.
    # At Task 1 no entry names a `keelline/guards/` file, so this iterates an empty list and
    # asserts nothing — vacuously true today. Task 2 appends the lane's first entry, which is
    # what starts exercising this assertion.
    text = (ROOT / "mutations.toml").read_text(encoding="utf-8")
    entries = [block for block in text.split("[[mutation]]") if "keelline/guards/" in block]
    for block in entries:
        assert offending(block) == [], block[:120]


@pytest.mark.parametrize("path", lane_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_lane_file_carries_a_source_repository_string(path: Path) -> None:
    assert offending(path.read_text(encoding="utf-8")) == [], path
