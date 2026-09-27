"""The shipped Python profile: it parses, it is neutral, and each check fires alone."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from keelline.profiles import detects, evaluate, load_profile, shipped
from tests.gitfixture import git, needs_git

CONFIGURED = """\
[project]
name = "widget"
requires-python = ">=3.11"

[tool.mypy]
strict = true

[tool.pytest.ini_options]
strict_markers = true
addopts = ["-ra"]

[tool.ruff.lint]
extend-select = ["B"]
"""
# The configured project with no pytest configuration at all, for the cases that supply one.
BARE = CONFIGURED.replace(
    '[tool.pytest.ini_options]\nstrict_markers = true\naddopts = ["-ra"]\n\n', ""
)


def _project(tmp_path: Path, pyproject: str = CONFIGURED, *, lock: bool = True) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    if lock:
        (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        git(tmp_path, "add", "uv.lock")
    return tmp_path


def _ids(root: Path) -> list[str]:
    return [o.check.id for o in evaluate(load_profile("python"), root)]


def test_python_is_shipped_and_parses() -> None:
    assert "python" in shipped()
    profile = load_profile("python")
    assert profile.scope and profile.rules.startswith("# ")
    # Two or three lines, and each one a bullet of the rules' own marked section.
    assert 2 <= len(profile.essentials) <= 3
    assert [c.id for c in profile.checks] == [
        "lockfile-absent",
        "lockfile-untracked",
        "requires-python",
        "requires-python-cap",
        "type-checker",
        "pytest-strict-markers",
        "pytest-addopts-marker",
        "ruff-legacy-select",
    ]


@needs_git
def test_a_configured_project_has_no_findings(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert detects(load_profile("python"), root)
    assert _ids(root) == []


@needs_git
@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (lambda t: t.replace('requires-python = ">=3.11"\n', ""), "requires-python"),
        (lambda t: t.replace('">=3.11"', '">=3.11,<4"'), "requires-python-cap"),
        (lambda t: t.replace('">=3.11"', '"==3.12.*"'), "requires-python-cap"),
        (lambda t: t.replace("[tool.mypy]\nstrict = true\n", ""), "type-checker"),
        (lambda t: t.replace("strict_markers = true\n", ""), "pytest-strict-markers"),
        (
            lambda t: t.replace("strict_markers = true\n", 'addopts = "--strict-config"\n').replace(
                'addopts = ["-ra"]\n', ""
            ),
            "pytest-strict-markers",
        ),
        (lambda t: t.replace('["-ra"]', '["-ra", "-m", "not slow"]'), "pytest-addopts-marker"),
        (
            lambda t: t.replace('extend-select = ["B"]', 'select = ["E", "F"]'),
            "ruff-legacy-select",
        ),
    ],
    ids=[
        "no-floor",
        "cap",
        "pinned-minor",
        "no-checker",
        "loose-markers",
        "strict-config-is-not-strict-markers",
        "addopts-marker",
        "legacy-select",
    ],
)
def test_each_pyproject_check_fires_alone(
    tmp_path: Path, edit: Callable[[str], str], expected: str
) -> None:
    # Advisory output, so the mutation stays here: the `addopts` pattern's `(\s|$)` back to
    # `\b` reddens `strict-config-is-not-strict-markers`.
    assert _ids(_project(tmp_path, edit(CONFIGURED))) == [expected]


@needs_git
@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("pyproject.toml", BARE + '\n[tool.pytest]\naddopts = ["--strict-markers"]\n'),
        ("pyproject.toml", BARE + '\n[tool.pytest.ini_options]\naddopts = ["-ra", "--strict"]\n'),
        ("pyproject.toml", BARE + '\n[tool.pytest.ini_options]\nstrict_markers = "True"\n'),
        ("pytest.toml", "[pytest]\nstrict_markers = true\n"),
        (".pytest.toml", "[pytest]\nstrict = true\n"),
        ("pytest.ini", "[pytest]\nstrict = true\n"),
        (".pytest.ini", "[pytest]\nstrict_markers = True\n"),
        ("pytest.ini", "[pytest]\naddopts = -ra --strict-markers\n"),
        ("setup.cfg", "[tool:pytest]\nstrict_markers = yes\n"),
        ("tox.ini", "[pytest]\nstrict_markers = 1\n"),
    ],
    ids=[
        "native-addopts",
        "addopts-strict",
        "string-true",
        "pytest.toml",
        "dot-pytest.toml",
        "pytest.ini-strict",
        "dot-pytest.ini",
        "ini-addopts",
        "setup.cfg",
        "tox.ini",
    ],
)
def test_every_configuration_pytest_reads_as_strict_counts_as_strict(
    tmp_path: Path, name: str, text: str
) -> None:
    # Each case is a project pytest 9.1.1 refuses an unregistered marker in (reproduced with
    # `@pytest.mark.typo`), and `BARE` alone is one it does not.
    root = _project(tmp_path, BARE)
    assert "pytest-strict-markers" in _ids(root)
    (root / name).write_text(text, encoding="utf-8")
    assert "pytest-strict-markers" not in _ids(root)


@needs_git
def test_the_two_lockfile_checks_fire_alone(tmp_path: Path) -> None:
    root = _project(tmp_path, lock=False)
    assert _ids(root) == ["lockfile-absent"]
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    assert _ids(root) == ["lockfile-untracked"]
    outcome = next(
        o for o in evaluate(load_profile("python"), root) if o.check.id == "lockfile-untracked"
    )
    # The lockfile that is untracked, and no other name the check could have found.
    assert outcome.located == ("uv.lock",)


@needs_git
def test_a_library_that_ignores_its_lock_on_purpose_is_left_alone(tmp_path: Path) -> None:
    root = _project(tmp_path, lock=False)
    (root / ".gitignore").write_text("uv.lock\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    assert _ids(root) == []


@needs_git
def test_a_poetry_classic_python_constraint_counts_as_a_floor(tmp_path: Path) -> None:
    text = CONFIGURED.replace('requires-python = ">=3.11"\n', "") + (
        '\n[tool.poetry.dependencies]\npython = ">=3.11"\n'
    )
    assert _ids(_project(tmp_path, text)) == []


def test_the_profile_prefers_no_type_checker_and_no_package_manager() -> None:
    # The neutrality claim, made checkable. The type-checker check accepts every checker it
    # names, and the essentials name every package manager they name, rather than one.
    profile = load_profile("python")
    checker = next(c for c in profile.checks if c.id == "type-checker")
    configured = {loc.toml or (loc.ini or ("",))[0] or loc.at for loc in checker.locators}
    for name in ("mypy", "pyright", "basedpyright", "pyrefly", "ty"):
        assert any(name in value for value in configured), name
    essentials = " ".join(profile.essentials)
    for tool in ("uv", "poetry", "pdm", "pipenv"):
        assert f"`{tool} run`" in essentials, tool
