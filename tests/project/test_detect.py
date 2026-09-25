"""The three values `init --yes` reads off a repository without asking."""

from __future__ import annotations

from pathlib import Path

import pytest

from keelline.errors import Refusal
from keelline.project.detect import Detected, detect
from tests.gitfixture import git, needs_git


def _repo(
    tmp_path: Path,
    name: str = "Widget",
    origin: str | None = "git@github.com:Owner/Widget.git",
) -> Path:
    root = tmp_path / name
    # `parents=True`: two cases below build their repository under a directory of their own, so
    # that three checkouts can exist under one `tmp_path` without nesting.
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    if origin:
        git(root, "remote", "add", "origin", origin)
    return root


@needs_git
def test_the_name_comes_from_origin_lower_cased_and_stripped(tmp_path: Path) -> None:
    assert detect(_repo(tmp_path)).name == "widget"
    assert detect(_repo(tmp_path / "b", origin="https://example.com/Owner/Gadget")).name == "gadget"
    assert detect(_repo(tmp_path / "c", name="Local", origin=None)) == Detected(
        "local", "main", ("claude", "codex")
    )


@needs_git
def test_the_base_branch_is_the_remotes_head_when_it_is_known(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/develop")
    assert detect(root).base_branch == "develop"


@needs_git
def test_a_base_branch_no_utf_8_file_can_hold_falls_back_to_the_default(tmp_path: Path) -> None:
    # git names refs in bytes, so `origin/HEAD` can point at a branch whose name is not UTF-8.
    # `git_run` now hands that name back surrogate-escaped instead of raising, and this value
    # is rendered into `keelline.toml`: `tomlout` keeps the escape as it is, and encoding the
    # document as UTF-8 raised `UnicodeEncodeError` out of `init` — measured, before its first
    # write. A name no file can record is no answer, the same as an `origin/HEAD` that is not
    # set. Mutation (declared): encode with `surrogateescape` -> the escape passes the check
    # and this reddens.
    root = _repo(tmp_path)
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/caf\udce9")
    assert detect(root).base_branch == "main"


@needs_git
def test_agents_are_the_surfaces_the_repository_carries(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / ".codex").mkdir()
    assert detect(root).agents == ("codex",)


@needs_git
def test_a_name_outside_the_grammar_is_refused_without_being_quoted(tmp_path: Path) -> None:
    # `+` is outside `PROJECT_NAME` (`_` is not — the grammar admits it). Mutation (oracle):
    # interpolate the value into the refusal -> the `not in` reddens.
    root = _repo(tmp_path, origin="git@github.com:Owner/My+Repo.git")
    with pytest.raises(Refusal) as caught:
        detect(root)
    assert "[project] name" in str(caught.value) and "my+repo" not in str(caught.value).lower()


@needs_git
def test_the_profile_is_the_one_whose_markers_the_repository_carries(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert detect(root).profile == ""
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    assert detect(root).profile == "python"
