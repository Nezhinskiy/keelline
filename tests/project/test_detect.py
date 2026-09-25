"""The four values `init --yes` reads off a repository without asking, and where each came from."""

from __future__ import annotations

from pathlib import Path

import pytest

from keelline.errors import Refusal
from keelline.project.detect import Detected, detect
from tests.gitfixture import git, needs_git
from tests.project.repos import repository

MIXED_CASE = "git@github.com:Owner/Widget.git"


@needs_git
def test_the_name_comes_from_origin_lower_cased_and_stripped(tmp_path: Path) -> None:
    assert detect(repository(tmp_path, origin=MIXED_CASE)).name == "widget"
    gadget = repository(tmp_path / "b", origin="https://example.com/Owner/Gadget")
    assert detect(gadget).name == "gadget"
    # No origin: the directory name, and every other value the default it falls back to, each
    # saying so.
    assert detect(repository(tmp_path / "c", origin=None, directory="Local")) == Detected(
        "local",
        "main",
        ("claude", "codex"),
        "",
        {
            "name": "directory name",
            "base_branch": "default",
            "agents": "default",
            "profile": "no profile markers",
        },
    )


@needs_git
def test_the_base_branch_is_the_remotes_head_when_it_is_known(tmp_path: Path) -> None:
    root = repository(tmp_path, origin=MIXED_CASE)
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
    found = detect(root)
    assert found.base_branch == "develop" and found.sources["base_branch"] == "origin/HEAD"


@needs_git
def test_a_remote_head_outside_the_branch_grammar_is_reported_as_the_default(
    tmp_path: Path,
) -> None:
    # `origin/HEAD` is written by `git clone` from what the remote says, so a branch named with
    # a backtick reaches this checkout and would reach `init --questions`' card and the workflow
    # `init` renders around it. Mutation (oracle): the grammar check reduced to "is it empty" ->
    # the branch comes back as detected and this reddens.
    root = repository(tmp_path, origin=MIXED_CASE)
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/`id`")
    found = detect(root)
    assert (found.base_branch, found.sources["base_branch"]) == ("main", "default")


@needs_git
def test_agents_are_the_surfaces_the_repository_carries(tmp_path: Path) -> None:
    root = repository(tmp_path, origin=MIXED_CASE)
    (root / ".codex").mkdir()
    found = detect(root)
    assert found.agents == ("codex",) and found.sources["agents"] == "harness directories"


@needs_git
def test_a_name_outside_the_grammar_is_refused_without_being_quoted(tmp_path: Path) -> None:
    # `+` is outside `PROJECT_NAME` (`_` is not — the grammar admits it). Mutation (oracle):
    # interpolate the value into the refusal -> the `not in` reddens.
    root = repository(tmp_path, origin="git@github.com:Owner/My+Repo.git")
    with pytest.raises(Refusal) as caught:
        detect(root)
    assert "[project] name" in str(caught.value) and "my+repo" not in str(caught.value).lower()


@needs_git
def test_leniently_a_name_outside_the_grammar_is_not_derivable(tmp_path: Path) -> None:
    # The same name, asked for rather than refused: `init --questions` leaves it to the person,
    # and never offers the repository's bytes as the default.
    found = detect(repository(tmp_path, origin="git@github.com:Owner/My+Repo.git"), lenient=True)
    assert (found.name, found.sources["name"]) == ("", "not derivable")


@needs_git
def test_the_profile_is_the_one_whose_markers_the_repository_carries(tmp_path: Path) -> None:
    root = repository(tmp_path, origin=MIXED_CASE)
    assert detect(root).profile == ""
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    found = detect(root)
    assert found.profile == "python" and found.sources["profile"] == "profile markers"
