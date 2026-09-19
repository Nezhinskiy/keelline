"""`overlay publish-template` (§5.9, §6.1, DC6): render, strip the ledger, push one commit
from the owner's checkout, and never without `--yes`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from keelline.errors import Failure, Refusal
from keelline.overlay.layout import OVERLAY_FILES
from keelline.overlay.publish import TEMPLATE_REPOSITORY, publish_template
from keelline.runner import NOT_FOUND, Completed
from keelline.scaffold import MANIFEST_PATH


@dataclass
class _GitHub:
    """`gh` and `git` as the publisher sees them: recorded, and the clone materialised.

    `git clone` has to leave a directory behind, or the publisher has nothing to write into;
    the stub creates it with one stale file, which the publisher must remove. `exists` says
    whether `gh repo view` answers.
    """

    exists: bool = True
    is_template: bool = True
    visibility: str = "PUBLIC"
    calls: list[tuple[list[str], Path]] = field(default_factory=list)
    pushed_tree: set[str] = field(default_factory=set)
    # The render, snapshotted where the clone is made beside it. The scratch directory is gone
    # when `publish_template` returns, and the render is the only place the scaffold ledger's
    # removal is observable at all — see the test that says so.
    rendered_tree: set[str] = field(default_factory=set)

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append((argv, cwd))
        if argv[:3] == ["gh", "repo", "view"]:
            if not self.exists:
                return Completed(1, "", "GraphQL: Could not resolve to a Repository")
            body = '{"isTemplate": %s, "visibility": "%s", "defaultBranchRef": {"name": "main"}}'
            marked = "true" if self.is_template else "false"
            return Completed(0, body % (marked, self.visibility), "")
        if argv[:3] == ["gh", "repo", "clone"]:
            rendered = cwd / "rendered"
            self.rendered_tree = {
                str(p.relative_to(rendered)) for p in rendered.rglob("*") if p.is_file()
            }
            target = cwd / argv[-1]
            (target / ".git").mkdir(parents=True)
            (target / "stale.md").write_text("old\n", encoding="utf-8")
            # A nested stale file as well as a loose one, because the two exercise different
            # halves of `_replace_tree`: the file walk removes both, and only the directory
            # walk takes `old/deep/` away afterwards.
            (target / "old" / "deep").mkdir(parents=True)
            (target / "old" / "deep" / "note.md").write_text("old\n", encoding="utf-8")
            return Completed(0, "", "")
        if argv[:2] == ["git", "-C"] and "status" in argv:
            return Completed(0, " M README.md\n?? hooks/hooks.json\n D stale.md\n", "")
        if argv[:2] == ["git", "-C"] and "push" in argv:
            clone = Path(argv[2])
            self.pushed_tree = {
                str(p.relative_to(clone))
                for p in clone.rglob("*")
                if p.is_file() and ".git" not in p.parts
            }
        return Completed(0, "", "")


def _argv(stub: _GitHub) -> list[list[str]]:
    return [argv for argv, _ in stub.calls]


def test_without_yes_everything_but_the_push_happens_and_the_push_is_named(tmp_path: Path) -> None:
    # The gate is on the one outward-facing act (Global Constraints: a flag a model can type
    # is not a control, so the gate is a parameter and the push is what it guards).
    # Mutation (declared): push regardless of `yes` -> `pushed` is True and reddens.
    stub = _GitHub()
    result = publish_template("Owner", yes=False, runner=stub)
    assert result.pushed is False
    assert not [a for a in _argv(stub) if "push" in a]
    assert any("re-run with --yes" in note for note in result.notes)
    assert result.repository == f"owner/{TEMPLATE_REPOSITORY}"


def test_without_yes_no_repository_is_created_or_marked(tmp_path: Path) -> None:
    # B9 of the plan's review: the first draft ran `gh repo create --public` and `gh repo edit
    # --template` BEFORE the `yes` gate, so the documented dry run created a public repository
    # on the owner's account. Mutation (declared): move `_ensure_repository` above the gate ->
    # both assertions redden.
    stub = _GitHub(exists=False)
    result = publish_template("owner", yes=False, runner=stub)
    argv = _argv(stub)
    assert not [a for a in argv if a[:3] == ["gh", "repo", "create"]]
    assert not [a for a in argv if a[:3] == ["gh", "repo", "edit"]]
    assert any("would create" in note for note in result.notes)


def test_a_dry_run_against_a_repository_that_is_not_public_promises_no_push(
    tmp_path: Path,
) -> None:
    # The dry run reports what `--yes` would do, so it must not promise a push that `--yes`
    # would refuse. The private case is the one where those two answers differ.
    stub = _GitHub(exists=True, is_template=False, visibility="PRIVATE")
    result = publish_template("owner", yes=False, runner=stub)
    assert result.pushed is False
    assert any("would refuse" in note for note in result.notes)
    assert not [note for note in result.notes if "re-run with --yes" in note]
    assert not [a for a in _argv(stub) if a[:3] == ["gh", "repo", "edit"]]


def test_an_existing_repository_that_is_not_public_is_refused_not_marked(tmp_path: Path) -> None:
    stub = _GitHub(exists=True, is_template=False, visibility="PRIVATE")
    with pytest.raises(Refusal, match="not public"):
        publish_template("owner", yes=True, runner=stub)
    assert not [a for a in _argv(stub) if a[:3] == ["gh", "repo", "edit"]]


def test_with_yes_the_rendered_tree_is_committed_and_pushed_without_the_ledger(
    tmp_path: Path,
) -> None:
    # The scratch tree is gone when `publish_template` returns, so the stub snapshots the
    # clone at push time (`_GitHub.pushed_tree`) and the assertions are over the snapshot.
    stub = _GitHub()
    result = publish_template("owner", yes=True, runner=stub)
    assert result.pushed is True
    written = stub.pushed_tree
    assert written == set(OVERLAY_FILES), written ^ set(OVERLAY_FILES)
    # This one guards `_replace_tree`'s whitelist and NOT the ledger strip: that function
    # writes only `OVERLAY_FILES`, so the ledger cannot reach the clone whether it was
    # stripped or not. Measured — with the strip deleted, all 74 cases in this directory still
    # passed. The strip has a case of its own below, over the render.
    assert str(MANIFEST_PATH) not in written
    assert "stale.md" not in written
    assert not [name for name in written if name.startswith("old/")]
    push = next(a for a in _argv(stub) if "push" in a)
    assert push[-1] == "HEAD:refs/heads/main"
    commit = next(a for a in _argv(stub) if "commit" in a)
    assert any(m.startswith("keelline overlay template ") for m in commit)


def test_a_missing_repository_is_created_public_and_marked_as_a_template(tmp_path: Path) -> None:
    # D1: the template is the PUBLIC half; §6.1: marked `is_template`. Mutation (declared):
    # drop `--public` -> reddens.
    stub = _GitHub(exists=False)
    publish_template("owner", yes=True, runner=stub)
    argv = _argv(stub)
    assert [
        "gh",
        "repo",
        "create",
        f"owner/{TEMPLATE_REPOSITORY}",
        "--public",
        "--description",
        "The template a Keelline private overlay is generated from",
    ] in argv
    assert ["gh", "repo", "edit", f"owner/{TEMPLATE_REPOSITORY}", "--template"] in argv


def test_an_existing_repository_not_yet_a_template_is_marked_and_not_recreated(
    tmp_path: Path,
) -> None:
    stub = _GitHub(exists=True, is_template=False)
    publish_template("owner", yes=True, runner=stub)
    argv = _argv(stub)
    assert not [a for a in argv if a[:3] == ["gh", "repo", "create"]]
    assert ["gh", "repo", "edit", f"owner/{TEMPLATE_REPOSITORY}", "--template"] in argv


def test_a_gh_that_cannot_run_is_a_failure_naming_it(tmp_path: Path) -> None:
    class _NoGh(_GitHub):
        def run(self, argv: list[str], cwd: Path) -> Completed:
            if argv[0] == "gh":
                return Completed(NOT_FOUND, "", "gh could not be run")
            return super().run(argv, cwd)

    with pytest.raises(Failure, match="gh repo view"):
        publish_template("owner", yes=True, runner=_NoGh())


def test_a_dry_run_against_a_public_repository_that_is_not_a_template_says_it_would_mark_it(
    tmp_path: Path,
) -> None:
    # The third arm of the dry-run report, and the one an owner meets on a second release
    # against a repository they created by hand. Without this the arm is written and unasserted.
    stub = _GitHub(exists=True, is_template=False, visibility="PUBLIC")
    result = publish_template("owner", yes=False, runner=stub)
    assert any("would mark" in note for note in result.notes)
    assert any("re-run with --yes" in note for note in result.notes)
    assert not [a for a in _argv(stub) if a[:3] == ["gh", "repo", "edit"]]


def test_a_template_that_is_already_current_is_not_committed_or_pushed(tmp_path: Path) -> None:
    # Idempotence, which is what makes "run it at every release" safe: `git status` reporting
    # nothing means the published tree is already this Keelline's, and an empty commit pushed
    # over it would be a release note for a release that changed nothing.
    class _Unchanged(_GitHub):
        def run(self, argv: list[str], cwd: Path) -> Completed:
            if argv[:2] == ["git", "-C"] and "status" in argv:
                self.calls.append((argv, cwd))
                return Completed(0, "", "")
            return super().run(argv, cwd)

    stub = _Unchanged()
    result = publish_template("owner", yes=True, runner=stub)
    assert result.pushed is False
    assert result.changed == ()
    assert any("nothing to push" in note for note in result.notes)
    assert not [a for a in _argv(stub) if "commit" in a or "push" in a]


def test_a_push_that_is_declined_is_a_failure_naming_the_repository(tmp_path: Path) -> None:
    # `gh` that could not be launched at all is the case above; this is the other one, and the
    # states have different remedies. A push refused by a ruleset or a lost credential must not
    # read as a publish that worked.
    class _RefusedPush(_GitHub):
        def run(self, argv: list[str], cwd: Path) -> Completed:
            recorded = super().run(argv, cwd)
            if argv[:2] == ["git", "-C"] and "push" in argv:
                return Completed(1, "", "remote: refused by a ruleset")
            return recorded

    with pytest.raises(Failure, match="refused by a ruleset"):
        publish_template("owner", yes=True, runner=_RefusedPush())


def test_the_render_the_publisher_clones_beside_carries_no_scaffold_ledger(tmp_path: Path) -> None:
    # Fix round 1, item 3. `scaffold.apply` writes `.keelline/manifest.json` into every local
    # render, and a repository generated from a template carries none — publishing one would
    # make every generated overlay read as hand-edited to `overlay upgrade` and never be
    # refreshed again. The assertion the plan gave for this was over the PUSHED tree, which
    # `_replace_tree`'s whitelist keeps clean on its own: deleting the strip left every case
    # in this file green. The strip is observable one step earlier, in the render, and the
    # stub snapshots it at clone time because the scratch directory is gone by the time
    # `publish_template` returns. Mutation (declared): drop the strip -> this reddens.
    stub = _GitHub()
    publish_template("owner", yes=True, runner=stub)
    assert stub.rendered_tree, "the stub never saw the render, so this asserts nothing"
    assert str(MANIFEST_PATH) not in stub.rendered_tree
    assert stub.rendered_tree == set(OVERLAY_FILES), stub.rendered_tree ^ set(OVERLAY_FILES)
