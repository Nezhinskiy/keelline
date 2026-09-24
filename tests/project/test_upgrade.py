"""`keelline upgrade`: moved keys, a re-planned footprint, and what it will not touch."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

import keelline
from keelline import fsops
from keelline.config.loader import CONFIG_FILE
from keelline.errors import Refusal
from keelline.project import footprint, templates
from keelline.project.upgrade import (
    NEWER,
    NO_RELEASE,
    NOT_INITIALISED,
    UNORDERED,
    UNREADABLE_VERSION,
    WORKFLOW_HELD,
    UpgradeReport,
    upgrade,
)
from keelline.scaffold import Manifest, Record, Verb, digest, engine
from keelline.scaffold.manifest import Kind, Location
from tests.gitfixture import LsRemote, needs_git
from tests.project.repos import initialised
from tests.snapshot import assert_snapshot_unchanged, snapshot

OLD = "a" * 40
NEW = "c" * 40
WORKFLOW = Path(".github") / "workflows" / "keelline.yml"
# `git ls-remote --exit-code` exits 2 when nothing matched, and 128 when it could not ask.
NO_TAG = LsRemote()
OFFLINE = LsRemote(code=128)


def _listing(version: str, sha: str) -> LsRemote:
    return LsRemote(stdout=f"{sha}\trefs/tags/v{version}\n", code=0)


def _pinned(tmp_path: Path) -> Path:
    return initialised(tmp_path, runner=_listing(keelline.__version__, OLD), ci=True)


def _upgrade(
    root: Path,
    tmp_path: Path,
    runner: LsRemote,
    *,
    dry_run: bool = False,
    force: tuple[str, ...] = (),
) -> UpgradeReport:
    return upgrade(
        root, machine=tmp_path / "absent.toml", runner=runner, dry_run=dry_run, force=force
    )


@pytest.fixture
def newer(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Become a later Keelline — a new version, one shipped template's bytes changed — when
    called, which is after the fixture has run the current one."""

    def become() -> None:
        monkeypatch.setattr(keelline, "__version__", "9.9.9")
        original = templates.read

        def read(name: str) -> str:
            text = original(name)
            extra = "\nA line the next release adds.\n"
            return text + extra if name == "documentation.md" else text

        monkeypatch.setattr(templates, "read", read)

    return become


@needs_git
def test_a_profile_kept_out_of_git_refuses_upgrade_before_anything_is_written(
    tmp_path: Path,
) -> None:
    # `footprint.refuse_local_profile` at the second entry point that writes a footprint: a
    # `keelline.toml` edited by hand after `init` meets it here. `uninstall` does not apply it, so
    # the same file can still be taken back. Mutation (oracle): "a profile artifact kept out of
    # git is written, and every pointer to it dangles" drops the condition both share.
    root = initialised(tmp_path)
    (root / CONFIG_FILE).write_text(
        f'[keelline]\nversion = "{keelline.__version__}"\nprofile = "python"\n'
        'agents = ["claude"]\n\n'
        '[project]\nname = "widget"\n\n[artifacts]\nlocal = ["claude-rules"]\n\n'
        '[ci]\nmode = "none"\n',
        encoding="utf-8",
    )
    before = snapshot(root)
    with pytest.raises(Refusal, match="profile's artifacts"):
        _upgrade(root, tmp_path, NO_TAG)
    assert_snapshot_unchanged(root, before)


@needs_git
def test_keelline_toml_kept_out_of_git_refuses_upgrade_before_any_write(tmp_path: Path) -> None:
    # `footprint.refuse_local_root_only` where a hand edit after `init` meets it.
    root = initialised(tmp_path)
    config = root / CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8") + '\n[artifacts]\nlocal = ["config"]\n',
        encoding="utf-8",
    )
    before = snapshot(root)
    with pytest.raises(Refusal) as refused:
        _upgrade(root, tmp_path, NO_TAG)
    assert_snapshot_unchanged(root, before)
    assert str(refused.value) == footprint.LOCAL_ROOT_ONLY.format(names="config")


@needs_git
def test_a_committed_path_into_keellines_own_directory_refuses_upgrade_before_any_write(
    tmp_path: Path,
) -> None:
    # The attach ledger case, end to end. `agents-md` is a region inserted into whatever file
    # `[paths] agents_md` names, so a pulled commit naming `.keelline/local/attach.json` had this
    # command report `region_update .keelline/local/attach.json (refreshed)` and rewrite the
    # ledger, in a directory git cannot give back. The loader refuses the value now, naming the
    # key. Mutation (oracle): "a [paths] value may name Keelline's own directory".
    root = initialised(tmp_path)
    ledger = root / ".keelline" / "local" / "attach.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text('{"entries": []}\n', encoding="utf-8")
    config = root / CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8")
        + '\n[paths]\nagents_md = ".keelline/local/attach.json"\n',
        encoding="utf-8",
    )
    before = snapshot(root)
    with pytest.raises(Refusal, match=r"paths\.agents_md names Keelline's own directory"):
        _upgrade(root, tmp_path, NO_TAG)
    assert_snapshot_unchanged(root, before)
    assert ledger.read_text(encoding="utf-8") == '{"entries": []}\n'


@needs_git
@pytest.mark.parametrize("runner", [_listing(keelline.__version__, OLD), NO_TAG, OFFLINE])
def test_a_current_footprint_upgrades_to_nothing_whatever_the_remote_answers(
    tmp_path: Path, runner: LsRemote
) -> None:
    root = _pinned(tmp_path)
    before = snapshot(root)
    report = _upgrade(root, tmp_path, runner)
    assert report.moved == ()
    # Nothing needed to move, so nothing was held: a note on every offline run of a current
    # project would say the pin was withheld when there was nothing to pin. Mutation
    # (advisory): `elif pinned and rewrite(text, changes) != text:` -> `elif pinned:` -> the
    # no-tag and offline cases redden.
    assert report.held == ""
    assert [a.verb for a in report.footprint.actions] == []
    assert_snapshot_unchanged(root, before)


@needs_git
def test_a_newer_keelline_refreshes_what_is_untouched_and_skips_what_was_edited(
    tmp_path: Path, newer: Callable[[], None]
) -> None:
    root = _pinned(tmp_path)
    running = keelline.__version__
    newer()
    roadmap = root / "docs" / "roadmap.md"
    roadmap.write_text(roadmap.read_text(encoding="utf-8") + "\nOur own line.\n", encoding="utf-8")
    document_before = (root / CONFIG_FILE).read_text(encoding="utf-8")

    report = _upgrade(root, tmp_path, _listing("9.9.9", NEW))

    # Keyed by artifact id, not by path: a document path under `tests/` is one of the strings
    # the neutrality gate refuses in test code.
    verbs = {a.artifact_id: (a.verb, a.reason) for a in report.footprint.actions}
    assert verbs["documentation-policy"] == (Verb.UPDATE, "refreshed")
    assert verbs["roadmap"] == (Verb.SKIP_MODIFIED, "hand-edited")
    assert "Our own line." in roadmap.read_text(encoding="utf-8")
    assert "A line the next release adds." in (
        root / "docs" / "architecture" / "documentation.md"
    ).read_text(encoding="utf-8")
    # Every byte but the two values is the byte it was.
    assert (root / CONFIG_FILE).read_text(encoding="utf-8") == document_before.replace(
        f'version = "{running}"', 'version = "9.9.9"'
    ).replace(OLD, NEW)
    assert f"@{NEW}\n" in (root / WORKFLOW).read_text(encoding="utf-8")
    assert [(m.key, m.after) for m in report.moved] == [
        ("keelline.version", "9.9.9"),
        ("ci.ref", NEW),
    ]


@needs_git
def test_force_overwrites_exactly_the_edit_it_names(
    tmp_path: Path, newer: Callable[[], None]
) -> None:
    root = _pinned(tmp_path)
    newer()
    for name in ("roadmap.md", "roadmap-history.md"):
        path = root / "docs" / name
        path.write_text(path.read_text(encoding="utf-8") + "\nours\n", encoding="utf-8")
    _upgrade(root, tmp_path, _listing("9.9.9", NEW), force=("docs/roadmap.md",))
    assert "ours" not in (root / "docs" / "roadmap.md").read_text(encoding="utf-8")
    assert "ours" in (root / "docs" / "roadmap-history.md").read_text(encoding="utf-8")


@needs_git
def test_a_dry_run_writes_nothing_and_reports_everything(
    tmp_path: Path, newer: Callable[[], None]
) -> None:
    root = _pinned(tmp_path)
    newer()
    before = snapshot(root)
    report = _upgrade(root, tmp_path, _listing("9.9.9", NEW), dry_run=True)
    assert report.dry_run and report.moved and report.footprint.actions
    assert_snapshot_unchanged(root, before)


@needs_git
@pytest.mark.parametrize("runner", [NO_TAG, OFFLINE])
def test_with_no_release_to_pin_neither_key_moves_and_the_report_says_why(
    tmp_path: Path, newer: Callable[[], None], runner: LsRemote
) -> None:
    # The workflow pins Keelline by commit, so `version`, `[ci] ref` and its `uses:` line are one
    # value. A version moved alone is a pull request that still runs the old Keelline.
    root = _pinned(tmp_path)
    newer()
    document = (root / CONFIG_FILE).read_text(encoding="utf-8")
    report = _upgrade(root, tmp_path, runner)
    assert report.moved == () and report.held == NO_RELEASE
    assert (root / CONFIG_FILE).read_text(encoding="utf-8") == document
    assert "A line the next release adds." in (
        root / "docs" / "architecture" / "documentation.md"
    ).read_text(encoding="utf-8")


@needs_git
def test_a_hand_edited_workflow_holds_both_keys_until_it_is_forced(
    tmp_path: Path, newer: Callable[[], None]
) -> None:
    root = _pinned(tmp_path)
    newer()
    workflow = root / WORKFLOW
    workflow.write_text(workflow.read_text(encoding="utf-8") + "# ours\n", encoding="utf-8")
    document = (root / CONFIG_FILE).read_text(encoding="utf-8")
    held = _upgrade(root, tmp_path, _listing("9.9.9", NEW))
    assert held.moved == () and held.held == WORKFLOW_HELD
    assert (root / CONFIG_FILE).read_text(encoding="utf-8") == document
    assert f"@{OLD}" in workflow.read_text(encoding="utf-8")

    forced = _upgrade(root, tmp_path, _listing("9.9.9", NEW), force=(WORKFLOW.as_posix(),))
    assert [m.key for m in forced.moved] == ["keelline.version", "ci.ref"] and not forced.held
    assert f"@{NEW}\n" in workflow.read_text(encoding="utf-8")


def _adopted(tmp_path: Path, ref: str, *, workflow: bool = True) -> tuple[Path, str]:
    """A repository that wrote its own `keelline.toml` pinning `ref`, and its own caller workflow
    around it when `workflow` says so, before `init` adopted it. Returns the root and the
    workflow's text."""
    document = (
        f'[keelline]\nversion = "{keelline.__version__}"\n\n[project]\nname = "widget"\n\n'
        f'[ci]\nref = "{ref}"\n'
    )
    text = (
        "# ours, from before Keelline\non: pull_request\njobs:\n  keelline:\n"
        f"    uses: {keelline.REPOSITORY_SLUG}/.github/workflows/check.yml@{ref}\n"
    )
    files = {WORKFLOW.as_posix(): text} if workflow else {}
    return initialised(tmp_path, document=document, files=files), text


@needs_git
def test_a_workflow_keelline_did_not_write_holds_both_keys_until_it_is_forced(
    tmp_path: Path, newer: Callable[[], None]
) -> None:
    # The caller workflow is the project's own, so Keelline never wrote it and holds no record of
    # it. Unforced, it stays byte for byte and so do version and ref, since the three are one
    # value. `--force` naming it is the remedy `WORKFLOW_HELD` gives, and it used to do nothing:
    # the engine's branch for a file with no record ignored `force`, so the run held for ever.
    # Mutation (oracle): "--force stops reaching a whole file Keelline did not write" -> the
    # forced run holds again, and the assertions after it redden.
    root, text = _adopted(tmp_path, OLD)
    running = keelline.__version__
    newer()
    workflow, config = root / WORKFLOW, root / CONFIG_FILE
    document = config.read_text(encoding="utf-8")
    held = _upgrade(root, tmp_path, _listing("9.9.9", NEW))
    assert held.moved == () and held.held == WORKFLOW_HELD
    verbs = {a.artifact_id: (a.verb, a.reason) for a in held.footprint.actions}
    assert verbs["ci-workflow"] == (Verb.SKIP_MODIFIED, "exists and Keelline did not write it")
    assert workflow.read_text(encoding="utf-8") == text
    assert config.read_text(encoding="utf-8") == document

    forced = _upgrade(root, tmp_path, _listing("9.9.9", NEW), force=(WORKFLOW.as_posix(),))
    assert [(m.key, m.after) for m in forced.moved] == [
        ("keelline.version", "9.9.9"),
        ("ci.ref", NEW),
    ]
    assert forced.held == ""
    assert config.read_text(encoding="utf-8") == document.replace(
        f'version = "{running}"', 'version = "9.9.9"'
    ).replace(OLD, NEW)
    rendered = workflow.read_text(encoding="utf-8")
    assert f"@{NEW}\n" in rendered and "# ours" not in rendered
    assert Manifest.read(root).get("ci-workflow") is not None


@needs_git
@pytest.mark.parametrize("workflow", [False, True], ids=["no-workflow", "own-workflow"])
def test_a_ref_that_is_not_a_commit_is_the_projects_and_only_the_version_moves(
    tmp_path: Path, newer: Callable[[], None], workflow: bool
) -> None:
    # `v1` is the documented opt-in to a moving Keelline, written by hand. It pins nothing this
    # command owns: `upgrade` replaced it with a sha and rendered a workflow over the choice, with
    # no note. Now only `[keelline] version` moves, and the ref and any workflow written around it
    # stay byte for byte. Mutation (oracle): "upgrade repins a [ci] ref that is not a commit".
    root, text = _adopted(tmp_path, "v1", workflow=workflow)
    running = keelline.__version__
    newer()
    config = root / CONFIG_FILE
    document = config.read_text(encoding="utf-8")
    report = _upgrade(root, tmp_path, _listing("9.9.9", NEW))
    assert [(m.key, m.after) for m in report.moved] == [("keelline.version", "9.9.9")]
    assert report.held == ""
    assert config.read_text(encoding="utf-8") == document.replace(
        f'version = "{running}"', 'version = "9.9.9"'
    )
    assert report.skipped["ci-workflow"] == templates.BAD_REF
    if workflow:
        assert (root / WORKFLOW).read_text(encoding="utf-8") == text
    else:
        assert not (root / WORKFLOW).exists()


@needs_git
def test_a_write_that_fails_part_way_leaves_the_pin_agreeing_and_the_next_run_converges(
    tmp_path: Path, newer: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The workflow's pin and `[ci] ref` are one value, and `keelline.toml` is written after the
    # whole footprint. Planned before the profile's artifacts, the workflow was already at the
    # new commit when a later write failed, while `keelline.toml` still recorded the old one,
    # and `doctor` reported the two apart until the next run. Planned last, a failure anywhere
    # before it leaves both on the old commit. Mutation (advisory): plan the workflow before the
    # profile's artifacts again -> the first assertion after the failure reddens.
    root = _pinned(tmp_path)
    config = root / CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "[keelline]\n", '[keelline]\nprofile = "python"\n', 1
        ),
        encoding="utf-8",
    )
    newer()
    original = fsops.write_within

    def failing(where: Path, target: str, payload: str) -> None:
        if target.endswith("/python.md"):
            raise OSError("no space left on device")
        original(where, target, payload)

    monkeypatch.setattr(engine, "write_within", failing)
    with pytest.raises(Refusal, match="cannot be written"):
        _upgrade(root, tmp_path, _listing("9.9.9", NEW))
    text = config.read_text(encoding="utf-8")
    assert f'ref = "{OLD}"' in text and f"@{OLD}\n" in (root / WORKFLOW).read_text(encoding="utf-8")

    monkeypatch.setattr(engine, "write_within", original)
    report = _upgrade(root, tmp_path, _listing("9.9.9", NEW))
    text = config.read_text(encoding="utf-8")
    assert 'version = "9.9.9"' in text and f'ref = "{NEW}"' in text
    assert f"@{NEW}\n" in (root / WORKFLOW).read_text(encoding="utf-8")
    assert [m.key for m in report.moved] == ["keelline.version", "ci.ref"]


@needs_git
@pytest.mark.parametrize("recorded", ["99.0.0", "99.0.0-rc1"])
def test_a_project_recording_a_newer_keelline_is_refused(tmp_path: Path, recorded: str) -> None:
    # An older plugin would repin an older release and put older bytes over newer ones. A
    # pre-release suffix does not hide the newer release: the leading `X.Y.Z` decides.
    root = _pinned(tmp_path)
    path = root / CONFIG_FILE
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f'version = "{keelline.__version__}"', f'version = "{recorded}"'
        ),
        encoding="utf-8",
    )
    before = snapshot(root)
    with pytest.raises(Refusal, match=re.escape(NEWER.format(running=keelline.__version__))):
        _upgrade(root, tmp_path, _listing(keelline.__version__, OLD))
    assert_snapshot_unchanged(root, before)


def _recording(root: Path, version: str) -> None:
    path = root / CONFIG_FILE
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f'version = "{keelline.__version__}"', f'version = "{version}"'
        ),
        encoding="utf-8",
    )


@needs_git
def test_a_pre_release_build_never_moves_a_project_recording_the_release_down_to_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Read by the leading `X.Y.Z` alone, `1.0.0` and `1.0.0rc1` were one version, so this build
    # rewrote a released `1.0.0` down to `1.0.0rc1` and re-pinned the workflow to it. Mutation
    # (oracle): "a release reads as older than its own pre-release" -> the run moves the version
    # and the refusal is never raised.
    root = initialised(tmp_path)
    _recording(root, "1.0.0")
    monkeypatch.setattr(keelline, "__version__", "1.0.0rc1")
    before = snapshot(root)
    with pytest.raises(Refusal) as refused:
        _upgrade(root, tmp_path, NO_TAG)
    assert str(refused.value) == NEWER.format(running="1.0.0rc1")
    assert_snapshot_unchanged(root, before)


@needs_git
def test_a_release_moves_a_project_recording_its_own_pre_release_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = initialised(tmp_path)
    _recording(root, "1.0.0.dev0")
    monkeypatch.setattr(keelline, "__version__", "1.0.0")
    report = _upgrade(root, tmp_path, NO_TAG)
    assert [(m.key, m.before, m.after) for m in report.moved] == [
        ("keelline.version", "(not a version)", "1.0.0")
    ]
    assert 'version = "1.0.0"\n' in (root / CONFIG_FILE).read_text(encoding="utf-8")


@needs_git
def test_two_pre_releases_of_one_version_are_refused_as_unordered_and_never_quoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `later` does not order two pre-releases, so which way a move would go is unknown. The
    # refusal names the running version, Keelline's own, and never the recorded string.
    # Mutation (oracle): "upgrade moves a version it cannot order" -> the run moves it.
    root = initialised(tmp_path)
    _recording(root, "1.0.0rc1-PROJECT")
    monkeypatch.setattr(keelline, "__version__", "1.0.0rc2")
    before = snapshot(root)
    with pytest.raises(Refusal) as refused:
        _upgrade(root, tmp_path, NO_TAG)
    assert str(refused.value) == UNORDERED.format(running="1.0.0rc2")
    assert "PROJECT" not in str(refused.value)
    assert_snapshot_unchanged(root, before)


@needs_git
def test_a_recorded_version_with_no_leading_triple_is_refused_and_never_quoted(
    tmp_path: Path,
) -> None:
    # `v99.0.0` has no leading `X.Y.Z`, so which way a move would go is unknown; moving it to the
    # running version could be moving it backward. Mutation (oracle): "upgrade moves a recorded
    # version it cannot read".
    root = _pinned(tmp_path)
    path = root / CONFIG_FILE
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f'version = "{keelline.__version__}"', 'version = "v99.0.0"'
        ),
        encoding="utf-8",
    )
    before = snapshot(root)
    with pytest.raises(Refusal, match=re.escape(UNREADABLE_VERSION)) as refused:
        _upgrade(root, tmp_path, _listing(keelline.__version__, OLD))
    assert "v99" not in str(refused.value)
    assert_snapshot_unchanged(root, before)


@needs_git
def test_an_uninitialised_repository_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    with pytest.raises(Refusal, match=re.escape(NOT_INITIALISED)):
        _upgrade(root, tmp_path, NO_TAG)


@needs_git
def test_a_record_naming_a_file_this_build_never_writes_is_counted_and_left(
    tmp_path: Path,
) -> None:
    # The manifest is committed, so a record is repository-authored. One claiming README.md
    # under an id this build does not produce, stamped with README.md's own bytes, must not make
    # `upgrade` touch it: which ids exist, and where each could be, are this build's. No
    # one-line mutation breaches this, because no code turns an unknown record into a template;
    # this case is the guard.
    root = _pinned(tmp_path)
    readme = root / "README.md"
    readme.write_text("# ours\n", encoding="utf-8")
    manifest = Manifest.read(root)
    manifest.with_record(
        Record(
            "readme",
            Kind.TEMPLATE,
            Location.REPO,
            "README.md",
            "project/x",
            "0.0.0",
            digest("# ours\n"),
        )
    ).write(root)
    report = _upgrade(root, tmp_path, _listing(keelline.__version__, OLD))
    assert readme.read_text(encoding="utf-8") == "# ours\n"
    assert report.orphans == 1


@needs_git
def test_switching_ci_off_retires_the_workflow_while_its_bytes_are_keellines(
    tmp_path: Path,
) -> None:
    root = _pinned(tmp_path)
    config = root / CONFIG_FILE
    # `init` wrote `[ci] ref` and left `mode` to the preset; the user now sets it.
    text = config.read_text(encoding="utf-8")
    assert "[ci]\n" in text
    config.write_text(text.replace("[ci]\n", '[ci]\nmode = "none"\n'), encoding="utf-8")
    report = _upgrade(root, tmp_path, NO_TAG)
    assert (Verb.REMOVE, WORKFLOW.as_posix()) in {
        (a.verb, a.target) for a in report.footprint.actions
    }
    assert not (root / WORKFLOW).exists()


@needs_git
def test_a_mode_this_build_does_not_render_is_not_a_request_to_delete_the_gate(
    tmp_path: Path,
) -> None:
    # `uvx` is a mode Keelline accepts and does not yet render, so `_ci` skips the workflow.
    # A skip is not a retirement, and the record is neither retired nor an orphan: the workflow
    # is where this build could have written it.
    root = _pinned(tmp_path)
    config = root / CONFIG_FILE
    text = config.read_text(encoding="utf-8")
    config.write_text(text.replace("[ci]\n", '[ci]\nmode = "uvx"\n'), encoding="utf-8")
    report = _upgrade(root, tmp_path, NO_TAG)
    assert (root / WORKFLOW).is_file()
    assert report.orphans == 0


@needs_git
def test_dropping_the_profile_retires_its_renditions_while_their_bytes_are_keellines(
    tmp_path: Path,
) -> None:
    root = initialised(tmp_path)
    config = root / CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "[keelline]\n", '[keelline]\nprofile = "python"\n', 1
        ),
        encoding="utf-8",
    )
    _upgrade(root, tmp_path, NO_TAG)
    assert (root / "docs" / "keelline" / "rules" / "python.md").is_file()
    config.write_text(
        config.read_text(encoding="utf-8").replace('profile = "python"\n', ""), encoding="utf-8"
    )
    report = _upgrade(root, tmp_path, NO_TAG)
    removed = {a.artifact_id for a in report.footprint.actions if a.verb is Verb.REMOVE}
    assert removed == {"profile-rules", "claude-rules"}
    assert not (root / "docs" / "keelline" / "rules" / "python.md").exists()
    assert report.orphans == 0


@needs_git
def test_an_edited_artifact_kept_out_of_git_is_left_and_named(tmp_path: Path) -> None:
    # A local artifact has no record, and its directory is git-ignored: an edit overwritten there
    # is gone for good. So it is judged against this build's bytes, and anything else is left.
    root = initialised(
        tmp_path,
        document=f'[keelline]\nversion = "{keelline.__version__}"\n\n[project]\nname = "widget"\n\n'
        '[artifacts]\nlocal = ["roadmap"]\n\n[ci]\nmode = "none"\n',
    )
    local = root / ".keelline" / "local" / "artifacts" / "docs" / "roadmap.md"
    local.write_text(local.read_text(encoding="utf-8") + "\nprivate plans\n", encoding="utf-8")
    report = _upgrade(root, tmp_path, NO_TAG)
    verbs = {a.artifact_id: a.verb for a in report.footprint.actions}
    assert verbs["roadmap"] is Verb.SKIP_MODIFIED
    assert "private plans" in local.read_text(encoding="utf-8")


@needs_git
def test_an_unedited_artifact_kept_out_of_git_follows_a_template_the_release_changed(
    tmp_path: Path, newer: Callable[[], None]
) -> None:
    # The ledger under `.keelline/local/` records what Keelline wrote there, so a copy nobody
    # touched is refreshed like a committed one. With the render as its only oracle it was
    # `skip_modified` after every release that changed its template, and `uninstall` refused
    # over it, calling it edited.
    root = initialised(
        tmp_path,
        document=f'[keelline]\nversion = "{keelline.__version__}"\n\n[project]\nname = "widget"\n'
        '\n[artifacts]\nlocal = ["documentation-policy"]\n\n[ci]\nmode = "none"\n',
    )
    newer()
    report = _upgrade(root, tmp_path, NO_TAG)
    verbs = {a.artifact_id: (a.verb, a.reason) for a in report.footprint.actions}
    assert verbs["documentation-policy"] == (Verb.UPDATE, "refreshed")
    local = root / ".keelline" / "local" / "artifacts" / "docs" / "architecture"
    assert "A line the next release adds." in (local / "documentation.md").read_text(
        encoding="utf-8"
    )


@needs_git
def test_forcing_a_left_copy_away_keeps_the_committed_file_recorded(tmp_path: Path) -> None:
    # The review's repro: `roadmap` taken out of `[artifacts] local` with its copy edited, so
    # `upgrade` skips the copy and creates and records `docs/roadmap.md`; forcing the copy away
    # then dropped that record by id, and the committed file was nobody's from then on.
    root = initialised(
        tmp_path,
        document=f'[keelline]\nversion = "{keelline.__version__}"\n\n[project]\nname = "widget"\n'
        '\n[artifacts]\nlocal = ["roadmap"]\n\n[ci]\nmode = "none"\n',
    )
    copy = ".keelline/local/artifacts/docs/roadmap.md"
    (root / copy).write_text("private plans\n", encoding="utf-8")
    config = root / CONFIG_FILE
    config.write_text(
        config.read_text(encoding="utf-8").replace('local = ["roadmap"]', "local = []"),
        encoding="utf-8",
    )
    _upgrade(root, tmp_path, NO_TAG)
    recorded = Manifest.read(root).get("roadmap")
    assert recorded is not None and recorded.target == "docs/roadmap.md"
    _upgrade(root, tmp_path, NO_TAG, force=(copy,))
    assert not (root / copy).exists()
    assert Manifest.read(root).get("roadmap") == recorded
