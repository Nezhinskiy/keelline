"""Which commit a change is judged against, and where in it the base's `keelline.toml` is.

Every case reads a real clone, because each defect here is git resolving a name or a path to
something other than what the caller meant: a tag answering for a remote-tracking ref, a
symlinked root answering for a directory the base never had. "No copy on the base" is the
bootstrap, which lets a change decide its own configuration, so every way of reaching it by
accident is a case.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import keelline
from keelline.assess.rule import (
    NOT_A_REPOSITORY,
    ROOT_UNANSWERED,
    local_base,
    read_base,
    repository_prefix,
)
from keelline.config.loader import load
from keelline.errors import Failure, Refusal
from tests.assess.baserepo import clone, commit, shadow
from tests.gitfixture import git, needs_git

pytestmark = needs_git

BASE = f"""[keelline]
version = "{keelline.__version__}"
state = "initialised"

[project]
name = "widget"
"""
REMOTE_MAIN = "refs/remotes/origin/main"


def default_base(root: Path) -> str:
    return local_base(load(root, machine=root.parent / "absent.toml"))


def test_the_default_base_is_the_remote_tracking_ref_whatever_a_tag_is_called(
    tmp_path: Path,
) -> None:
    # A tag spelled `origin/main` wins git's lookup of the short name over the remote-tracking
    # ref, and it carries no `keelline.toml`: read by the short name, the base would be the
    # bootstrap. The default names the ref in full, so no tag can stand in for it.
    project = clone(tmp_path, BASE)
    shadow(project, "origin/main")
    assert read_base(project, default_base(project)) == BASE


def test_a_short_name_is_refused_because_a_tag_can_take_its_place(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    shadow(project, "origin/main")
    with pytest.raises(Refusal, match="refs/"):
        read_base(project, "origin/main")


def test_a_full_ref_name_must_exist_as_itself(tmp_path: Path) -> None:
    # With no `refs/remotes/origin/gone`, git would resolve the name to the tag
    # `refs/tags/refs/remotes/origin/gone`, whose commit has no `keelline.toml`.
    project = clone(tmp_path, BASE)
    shadow(project, "refs/remotes/origin/gone")
    with pytest.raises(Failure, match=re.escape("fetch-depth: 0")):
        read_base(project, "refs/remotes/origin/gone")


def test_a_commit_id_is_read_as_given(tmp_path: Path) -> None:
    # What CI passes: the id the workflow resolved once from the remote-tracking ref. Removing
    # the 40-hex alternative from the shape refuses more, so it is not declared as a mutation.
    project = clone(tmp_path, BASE)
    sha = git(project, "rev-parse", REMOTE_MAIN).strip()
    assert read_base(project, sha) == BASE


def test_a_project_in_a_subdirectory_reads_the_base_s_copy_at_its_own_path(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE, under="sub")
    assert repository_prefix(project / "sub") == "sub/"
    assert read_base(project / "sub", REMOTE_MAIN) == BASE
    assert read_base(project, REMOTE_MAIN) is None


def test_a_project_root_moved_behind_a_symlink_is_refused(tmp_path: Path) -> None:
    # The change moves the project and leaves a link where it was: git resolves the link and
    # looks for `newdir/keelline.toml` on the base, which has none, so the change would be the
    # bootstrap and decide its own configuration.
    project = clone(tmp_path, BASE, under="sub")
    git(project, "mv", "sub", "newdir")
    os.symlink("newdir", project / "sub")
    commit(project, "chore: move the project")
    with pytest.raises(Refusal, match="symlink"):
        read_base(project / "sub", REMOTE_MAIN)


def test_a_component_linked_back_to_the_repository_s_top_is_refused(tmp_path: Path) -> None:
    # `app -> .` resolves to the top as well, so an ancestor search from the nearest end would
    # stop at `app` and read `sub/` as the prefix, where the base keeps `app/sub/`.
    project = clone(tmp_path, BASE, under="app/sub")
    git(project, "mv", "app/sub", "sub")
    if (project / "app").exists():
        (project / "app").rmdir()
    os.symlink(".", project / "app")
    commit(project, "chore: link the old place back to the top")
    with pytest.raises(Refusal, match="symlink"):
        read_base(project / "app" / "sub", REMOTE_MAIN)


def test_a_link_above_the_repository_is_the_machine_s_and_is_admitted(tmp_path: Path) -> None:
    # `/tmp` on macOS, a symlinked home, a logical `$PWD`: a link above the repository is not
    # the repository's to author. A first draft refused any root that did not equal its own
    # resolution, which refuses more, so it is not declared as a mutation.
    real = tmp_path / "real"
    real.mkdir()
    project = clone(real, BASE)
    os.symlink(real, tmp_path / "link")
    through = tmp_path / "link" / project.name
    assert repository_prefix(through) == ""
    assert read_base(through, REMOTE_MAIN) == BASE


@pytest.mark.parametrize(
    "spelling", ["project/SUB", "PROJECT/sub"], ids=["below-the-top", "the-top"]
)
def test_a_root_spelled_otherwise_than_git_spells_it_is_refused(
    spelling: str, tmp_path: Path
) -> None:
    project = clone(tmp_path, BASE, under="sub")
    if not (project / "SUB").exists():
        pytest.skip("this file system tells `SUB` from `sub`")
    # On a case-folding disk `SUB` is `sub`, but the base has no `SUB/keelline.toml`. Spelled
    # otherwise at the top itself, no ancestor of the root resolves to git's top at all: removing
    # that refusal reddens `the-top`. Not declared as a mutation, because both cases skip on the
    # Linux runner the oracle uses.
    with pytest.raises(Refusal, match="symlink"):
        read_base(tmp_path / spelling, REMOTE_MAIN)


def test_git_failing_to_list_the_base_is_a_failure_and_never_the_bootstrap(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE)
    tree = git(project, "rev-parse", f"{REMOTE_MAIN}^{{tree}}").strip()
    loose = project / ".git" / "objects" / tree[:2] / tree[2:]
    assert loose.is_file(), "the case needs the base's tree as a loose object"
    loose.unlink()
    with pytest.raises(Failure, match=re.escape("fetch-depth: 0")):
        read_base(project, REMOTE_MAIN)


def test_a_base_copy_that_is_not_utf8_is_a_failure_and_never_the_bootstrap(
    tmp_path: Path,
) -> None:
    # `git_run` answers `(-1, "")` when git's output is not UTF-8. Read as "listed nothing" or as
    # an empty document, the change would govern itself, or be judged against no configuration.
    project = clone(tmp_path, b'[keelline]\nversion = "\xff"\n')
    (project / "keelline.toml").write_text(BASE, encoding="utf-8")
    with pytest.raises(Failure, match=re.escape("fetch-depth: 0")):
        read_base(project, default_base(project))


def test_a_root_outside_any_repository_is_a_failure(tmp_path: Path) -> None:
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    with pytest.raises(Failure, match=re.escape(NOT_A_REPOSITORY)):
        read_base(nowhere, REMOTE_MAIN)


def test_a_repository_git_will_not_answer_for_is_not_called_no_repository(
    tmp_path: Path,
) -> None:
    # A worktree whose git directory is gone: git exits 128 exactly as outside a repository, and
    # a CI checkout of dubious ownership does the same. Both fail; the message must not send the
    # owner looking for a repository that is there. Raising `NOT_A_REPOSITORY` whatever the disk
    # says reddens this; it is wording, not permission, so it has no oracle entry.
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / ".git").write_text(f"gitdir: {tmp_path / 'gone'}\n", encoding="utf-8")
    with pytest.raises(Failure, match=re.escape(ROOT_UNANSWERED)):
        read_base(broken, REMOTE_MAIN)
