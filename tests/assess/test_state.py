"""`keelline adopt begin` and `keelline adopt promote`: the state machine that moves one gate at a
time from advisory to enforcing, over a repository `init --yes` wrote and two commits made.

Every promotion is judged against the first commit, named by its full id: the fixture has an
origin but no remote-tracking ref, so the default base does not exist and `plan` and `commit`
would have no range. From that commit, `plan` lints the one adoption plan and `commit` checks one
message, and all five built-in gates pass on the tree as `_project` leaves it.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from keelline.assess.state import begin, promote
from keelline.cli import build_parser, discover_registrars, run
from keelline.config.loader import CONFIG_FILE, load, preset_defaults
from keelline.config.owned import OwnedKeyError
from keelline.config.schema import BUILTIN_GATES, Config
from keelline.errors import Failure, Refusal
from keelline.project.templates import CONFIG_ARTIFACT
from keelline.project.upgrade import upgrade
from keelline.scaffold import Manifest, ManifestError, digest
from tests.gitfixture import LsRemote, git, needs_git
from tests.project.repos import repository

pytestmark = needs_git

PLAN = "# Adoption\n\n**Scope:** adoption.\n\n**Premise:** none.\n"
PLANS = preset_defaults("widget").paths.plans
ADOPTION = f"{PLANS}/2026-09-23-keelline-adoption.md"
# Well past the preset's `AGENTS.md` budget, so the `docs` gate has a finding.
OVER_BUDGET = "".join("word\n" for _ in range(400))
MARKER = "marker"


def _cli(root: Path, tmp_path: Path, *argv: str) -> tuple[int, str, str]:
    parser = build_parser(discover_registrars())
    flags = ["--root", str(root), "--machine", str(tmp_path / "m.toml")]
    with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
        code = run([*argv, *flags], parser=parser)
    return code, out.getvalue(), err.getvalue()


def _project(tmp_path: Path) -> tuple[Path, str]:
    """A repository `init --yes --no-ci` wrote, committed, then an adoption plan committed with
    the trail that lists it; the root, and the first commit's full id.

    The plan is staged before `docs trail` runs, because the trail lists tracked files only:
    regenerated first, it would be stale once the plan is committed.
    """
    root = repository(tmp_path)
    code, _, err = _cli(root, tmp_path, "init", "--yes", "--no-ci")
    assert code == 0, err
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: adopt keelline")
    (root / ADOPTION).write_text(PLAN, encoding="utf-8")
    git(root, "add", "-A")
    code, _, err = _cli(root, tmp_path, "docs", "trail")
    assert code == 0, err
    git(root, "add", "-A")
    git(root, "commit", "-qm", "docs: the keelline adoption plan")
    return root, git(root, "rev-parse", "HEAD~1").strip()


def _config(root: Path, tmp_path: Path) -> Config:
    return load(root, machine=tmp_path / "m.toml")


def _document(root: Path) -> str:
    return (root / CONFIG_FILE).read_text(encoding="utf-8")


def _set(root: Path, old: str, new: str) -> None:
    """Replace `old` in `keelline.toml`, once, by `new`."""
    text = _document(root)
    assert text.count(old) == 1, old
    (root / CONFIG_FILE).write_text(text.replace(old, new), encoding="utf-8")


def _custom(name: str, code: str) -> str:
    """A `[gates.custom.<name>]` table running `code` under this interpreter."""
    return f"\n[gates.custom.{name}]\nrun = {json.dumps([sys.executable, '-c', code])}\n"


def _with_marker_gate(root: Path) -> None:
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write(_custom(MARKER, f"open({MARKER!r}, 'w').close()"))


def test_begin_marks_adopting_and_keeps_every_other_byte_and_the_record(tmp_path: Path) -> None:
    # Mutation: `begin` calling `rewrite_owned` with `"installed"` -> the byte equality reddens;
    # skipping the manifest's re-stamp in `rewrite_owned` -> the digest equality reddens.
    root, _ = _project(tmp_path)
    before = _document(root)
    transition = begin(root, _config(root, tmp_path), root / ADOPTION)
    assert (transition.before, transition.after) == ("initialised", "adopting")
    after = _document(root)
    assert before.count('state = "initialised"') == 1
    assert after == before.replace('state = "initialised"', 'state = "adopting"')
    record = Manifest.read(root).get(CONFIG_ARTIFACT)
    assert record is not None
    assert record.sha256 == digest(after)


def test_begin_refuses_a_plan_that_is_not_an_adoption_plan(tmp_path: Path) -> None:
    # Mutation (declared): the name check made `if False:` -> both plans pass `plan check`, so
    # `begin` marks the project adopting instead of refusing.
    root, _ = _project(tmp_path)
    at_root = root / "2026-09-24-keelline-adoption.md"
    unnamed = root / PLANS / "2026-09-24-widget.md"
    for plan in (at_root, unnamed):
        plan.write_text(PLAN, encoding="utf-8")
        with pytest.raises(Refusal, match="adoption plan"):
            begin(root, _config(root, tmp_path), plan)
        assert _config(root, tmp_path).keelline.state == "initialised"


def test_begin_refuses_a_plan_outside_the_root_or_absent(tmp_path: Path) -> None:
    # Both are refused before `plan check` reads anything, and in the same words: a message that
    # named the path would print what the caller typed back to it, and the rule is one sentence.
    # Mutation (declared): the file-and-containment check made `if False:` -> the absent plan
    # reaches `plan check`, which fails rather than refuses, and the one outside the root raises
    # `ValueError` from `relative_to`.
    root, _ = _project(tmp_path)
    outside = tmp_path / PLANS / "2026-09-24-keelline-adoption.md"
    outside.parent.mkdir(parents=True)
    outside.write_text(PLAN, encoding="utf-8")
    for plan in (outside, root / PLANS / "2026-09-25-keelline-adoption.md"):
        with pytest.raises(Refusal, match="adoption plan"):
            begin(root, _config(root, tmp_path), plan)
    assert _config(root, tmp_path).keelline.state == "initialised"


def test_begin_fails_an_adoption_plan_that_fails_plan_check(tmp_path: Path) -> None:
    # Mutation (declared): `if findings:` made `if False:` -> the plan with no scope line is
    # accepted and the project marked adopting.
    root, _ = _project(tmp_path)
    before = _document(root)
    (root / ADOPTION).write_text("# no scope, no premise\n", encoding="utf-8")
    with pytest.raises(Failure, match="plan check"):
        begin(root, _config(root, tmp_path), root / ADOPTION)
    assert _document(root) == before


def test_begin_never_moves_an_installed_project_back(tmp_path: Path) -> None:
    # Mutation (declared): `if state != "initialised":` made `if False:` -> `begin` writes
    # `adopting` over `installed`.
    root, base = _project(tmp_path)
    promote(root, _config(root, tmp_path), [], base=base)
    before = _document(root)
    transition = begin(root, _config(root, tmp_path), root / ADOPTION)
    assert (transition.before, transition.after) == ("installed", "installed")
    assert _document(root) == before


def test_a_named_gate_that_passes_is_enforced_without_begin_first(tmp_path: Path) -> None:
    # Promotion is its own step: nothing requires `begin` first, and the first promotion moves
    # an initialised project to adopting, since the loader refuses a list under `initialised`.
    # Mutation: `after` kept at the current state when not installing -> `enforced` is written
    # under `initialised`, and reloading the document refuses it.
    root, base = _project(tmp_path)
    transition = promote(root, _config(root, tmp_path), ["docs"], base=base)
    assert (transition.before, transition.after, transition.promoted) == (
        "initialised",
        "adopting",
        ("docs",),
    )
    assert _config(root, tmp_path).keelline.enforced == ("docs",)


def test_named_gates_are_promoted_all_together_or_not_at_all(tmp_path: Path) -> None:
    # Mutation (declared): the write condition made `if not promoted:` -> `bugs` is written
    # although `docs`, named beside it, failed.
    root, base = _project(tmp_path)
    (root / "AGENTS.md").write_text(OVER_BUDGET, encoding="utf-8")
    before = _document(root)
    transition = promote(root, _config(root, tmp_path), ["docs", "bugs"], base=base)
    assert transition.promoted == ()
    assert set(transition.failing) == {"docs"}
    assert (transition.before, transition.after) == ("initialised", "initialised")
    assert _document(root) == before


def test_with_no_names_every_passing_gate_is_enforced_and_the_rest_are_named(
    tmp_path: Path,
) -> None:
    # Mutation (declared): the write condition made `if failing or unanswered or not promoted:`
    # -> nothing is written once `docs` fails, and the four that passed stay advisory.
    root, base = _project(tmp_path)
    (root / "AGENTS.md").write_text(OVER_BUDGET, encoding="utf-8")
    transition = promote(root, _config(root, tmp_path), [], base=base)
    passing = tuple(name for name in BUILTIN_GATES if name != "docs")
    assert transition.promoted == passing
    assert list(transition.failing) == ["docs"]
    assert transition.failing["docs"] > 0
    assert transition.unanswered == ()
    loaded = _config(root, tmp_path).keelline
    assert (loaded.state, loaded.enforced) == ("adopting", passing)


def test_promoting_every_configured_gate_installs_the_project(tmp_path: Path) -> None:
    # Mutation (declared): `after = "adopting"` always -> the state stays adopting with every
    # gate listed.
    root, base = _project(tmp_path)
    transition = promote(root, _config(root, tmp_path), [], base=base)
    assert (transition.after, transition.promoted, transition.failing) == (
        "installed",
        BUILTIN_GATES,
        {},
    )
    assert "enforced = []" in _document(root)
    loaded = _config(root, tmp_path).keelline
    assert loaded.state == "installed"
    assert loaded.enforcing == frozenset(BUILTIN_GATES)


def test_nothing_left_to_promote_on_an_installed_project_is_refused_rather_than_rewritten(
    tmp_path: Path,
) -> None:
    # In-comment, not declared: the bare call's refusal guards no write, since without it an
    # installed project is "completed" to the bytes it already holds. Mutation: `raise
    # Refusal(ALL_ENFORCE)` made `return Transition(state, state)` -> the second bare call
    # returns, and the `pytest.raises` reddens.
    root, base = _project(tmp_path)
    promote(root, _config(root, tmp_path), ["docs"], base=base)
    with pytest.raises(Refusal, match="already enforces"):
        promote(root, _config(root, tmp_path), ["docs"], base=base)
    promote(root, _config(root, tmp_path), [], base=base)
    before = _document(root)
    with pytest.raises(Refusal, match="already enforces"):
        promote(root, _config(root, tmp_path), [], base=base)
    assert _document(root) == before


def test_an_adopting_project_whose_every_gate_enforces_is_completed_to_installed(
    tmp_path: Path,
) -> None:
    # A project that removed the one gate it had not promoted: every configured gate enforces
    # and the state still says adopting, so a bare `promote` completes it without running one.
    # Mutation (declared): the completion's branch made to refuse as under `installed` -> the
    # bare call raises the "nothing left" refusal, and this case alone reddens.
    root, base = _project(tmp_path)
    kept = [name for name in BUILTIN_GATES if name != "trail"]
    listed = ", ".join(f'"{name}"' for name in (*kept, MARKER))
    _set(
        root,
        'state = "initialised"\n',
        f'state = "adopting"\nenforced = [{listed}]\n',
    )
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write("\n[gates]\nbuiltin = [" + ", ".join(f'"{n}"' for n in kept) + "]\n")
    _with_marker_gate(root)
    transition = promote(root, _config(root, tmp_path), [], base=base)
    assert (transition.before, transition.after, transition.promoted) == (
        "adopting",
        "installed",
        (),
    )
    assert not (root / MARKER).exists()
    loaded = _config(root, tmp_path).keelline
    assert loaded.state == "installed"
    assert "enforced = []" in _document(root)


def test_an_initialised_project_with_no_gate_is_refused_rather_than_installed(
    tmp_path: Path,
) -> None:
    # With nothing configured nothing is wanted, and the completion that is right for an
    # adopting project would install one that never earned a gate. Mutation (declared): the
    # refusal's condition made `if False:` -> the project is written `installed`.
    root, base = _project(tmp_path)
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write("\n[gates]\nbuiltin = []\n")
    before = _document(root)
    with pytest.raises(Refusal, match="configures no gate"):
        promote(root, _config(root, tmp_path), [], base=base)
    assert _document(root) == before


def test_a_completion_the_editor_cannot_write_names_both_keys_as_they_will_be(
    tmp_path: Path,
) -> None:
    # An adopting project whose every gate enforces, listed over several lines. The editor
    # sets `enforced` first and refused it naming `enforced = []` alone; followed beside
    # `state = "adopting"`, that loads with nothing enforcing, every earned gate demoted. The
    # remedy names both keys as the completion writes them, and following it installs.
    # Mutation (declared): the editor's own refusal re-raised -> the message lacks the state.
    root, base = _project(tmp_path)
    multiline = "".join(f'  "{name}",\n' for name in BUILTIN_GATES)
    _set(root, 'state = "initialised"\n', f'state = "adopting"\nenforced = [\n{multiline}]\n')
    before = _document(root)
    with pytest.raises(OwnedKeyError) as refused:
        promote(root, _config(root, tmp_path), [], base=base)
    message = str(refused.value)
    assert '`state = "installed"`' in message
    assert "`enforced = []`" in message
    assert _document(root) == before
    (root / CONFIG_FILE).write_text(
        before.replace(
            f'state = "adopting"\nenforced = [\n{multiline}]\n',
            'state = "installed"\nenforced = []\n',
        ),
        encoding="utf-8",
    )
    loaded = _config(root, tmp_path).keelline
    assert loaded.state == "installed"
    assert loaded.enforcing == frozenset(BUILTIN_GATES)


def test_a_named_gate_already_enforcing_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    # In-comment, not declared: this refusal guards no write the all-or-nothing rule does not
    # already hold; dropping it re-runs `docs` and writes the same list plus `bugs`.
    root, base = _project(tmp_path)
    promote(root, _config(root, tmp_path), ["docs"], base=base)
    before = _document(root)
    with pytest.raises(Refusal, match="already enforces"):
        promote(root, _config(root, tmp_path), ["docs", "bugs"], base=base)
    assert _document(root) == before


def test_a_name_that_is_not_a_configured_gate_is_refused(tmp_path: Path) -> None:
    # In-comment, not declared: without it `run_gates` raises `KeyError` on the name, which the
    # frame reports as an internal error; nothing is written either way.
    root, base = _project(tmp_path)
    for name in ("config", "lint"):
        with pytest.raises(Refusal, match="configured gate"):
            promote(root, _config(root, tmp_path), [name], base=base)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param(
            'state = "initialised"\n',
            'state = "initialised"\nenforced = [\n]\n',
            id="a-two-line-enforced",
        ),
        pytest.param('state = "initialised"\n', '"state" = "initialised"\n', id="a-quoted-state"),
    ],
)
def test_an_enforced_list_the_editor_cannot_rewrite_is_refused_before_any_gate_runs(
    tmp_path: Path, old: str, new: str
) -> None:
    # Mutation (declared): the trial rewrite made `pass` -> the marker gate runs before the
    # write refuses, so the marker appears.
    #
    # The remedy names what the document holds now. The trial sets made-up values, and passing
    # the editor's own refusal on told the person to write them: `state = "installed"`, which
    # enforces every gate with none of them earned, or `enforced = ["config"]`, which does not
    # load. Mutation: re-raising the editor's refusal unchanged -> the message assertions redden.
    root, base = _project(tmp_path)
    _set(root, old, new)
    _with_marker_gate(root)
    before = _document(root)
    with pytest.raises(OwnedKeyError) as refused:
        promote(root, _config(root, tmp_path), [], base=base)
    message = str(refused.value)
    assert '`state = "initialised"`' in message
    assert "`enforced = []`" in message
    assert "installed" not in message
    assert "config" not in message
    assert not (root / MARKER).exists()
    assert _document(root) == before


def test_an_uneditable_document_s_remedy_names_the_list_as_it_stands(tmp_path: Path) -> None:
    # An adopting project whose list is written over two lines: the remedy gives the list it
    # holds, one line, and not the trial's.
    root, base = _project(tmp_path)
    _set(root, 'state = "initialised"\n', 'state = "adopting"\nenforced = [\n  "docs",\n]\n')
    with pytest.raises(OwnedKeyError) as refused:
        promote(root, _config(root, tmp_path), [], base=base)
    message = str(refused.value)
    assert '`state = "adopting"`' in message
    assert '`enforced = ["docs"]`' in message
    assert "config" not in message


def test_a_manifest_the_write_cannot_read_is_refused_before_any_gate_runs(tmp_path: Path) -> None:
    # The write re-stamps the manifest's record of `keelline.toml`, so a manifest that does not
    # parse refuses the write; found only there, it was found after every gate, a custom
    # command included, had run. Mutation (declared): the pre-check's `Manifest.read` made
    # `pass` -> the marker gate runs and the marker appears.
    root, base = _project(tmp_path)
    _with_marker_gate(root)
    manifest = root / ".keelline" / "manifest.json"
    manifest.write_text("{not json", encoding="utf-8")
    before = _document(root)
    with pytest.raises(ManifestError):
        promote(root, _config(root, tmp_path), [], base=base)
    assert not (root / MARKER).exists()
    assert _document(root) == before


def test_a_custom_gate_runs_its_command_when_promoted(tmp_path: Path) -> None:
    # A custom gate is promoted as a built-in is: its command runs, and its name joins the list.
    # Mutation: `run_gates` handed only the built-in names of `wanted` -> nothing runs, nothing
    # is promoted, and the marker is absent.
    root, base = _project(tmp_path)
    _with_marker_gate(root)
    transition = promote(root, _config(root, tmp_path), [MARKER], base=base)
    assert (root / MARKER).exists()
    assert transition.promoted == (MARKER,)
    assert _config(root, tmp_path).keelline.enforced == (MARKER,)


def test_adopt_begin_json_carries_the_state_on_each_side_and_nothing_else(tmp_path: Path) -> None:
    # `begin` runs no gate, so its document has no gate keys to leave empty. Mutation: passing
    # the promotion's document to `Result` -> the key set reddens.
    root, _ = _project(tmp_path)
    code, out, err = _cli(root, tmp_path, "adopt", "begin", str(root / ADOPTION), "--json")
    assert code == 0, err
    printed = json.loads(out)
    assert {k: v for k, v in printed.items() if k != "summary"} == {
        "before": "initialised",
        "after": "adopting",
    }


def test_a_promotion_is_what_the_gate_enforces_next(tmp_path: Path) -> None:
    # Mutation (declared): the write made to carry `state` alone -> `enforced` stays empty, so
    # the second `gate` still prints `docs: advisory`.
    root, _ = _project(tmp_path)
    head = git(root, "rev-parse", "HEAD").strip()
    code, out, err = _cli(root, tmp_path, "adopt", "begin", str(root / ADOPTION))
    assert code == 0, err
    assert "adopting" in out
    assert _config(root, tmp_path).keelline.state == "adopting"
    code, out, err = _cli(root, tmp_path, "gate", "--only", "docs", "--base", head)
    assert (code, out.splitlines()) == (0, ["docs: advisory, 0 finding(s)"]), err
    code, out, err = _cli(root, tmp_path, "adopt", "promote", "docs", "--base", head, "--json")
    assert code == 0, err
    printed = json.loads(out)
    assert (printed["promoted"], printed["failing"]) == (["docs"], {})
    code, out, err = _cli(root, tmp_path, "gate", "--only", "docs", "--base", head)
    assert (code, out.splitlines()) == (0, ["docs: enforcing, 0 finding(s)"]), err


def test_the_command_exits_1_when_a_gate_failed_and_reports_both_lists(tmp_path: Path) -> None:
    # Mutation (declared): `exit_code=1 if advisory else 0` dropped -> exits 0 with `docs` still
    # advisory.
    root, base = _project(tmp_path)
    (root / "AGENTS.md").write_text(OVER_BUDGET, encoding="utf-8")
    code, out, err = _cli(root, tmp_path, "adopt", "promote", "--base", base, "--json")
    assert code == 1, err
    printed = json.loads(out)
    assert printed["promoted"] == [name for name in BUILTIN_GATES if name != "docs"]
    assert list(printed["failing"]) == ["docs"]
    assert (printed["before"], printed["after"]) == ("initialised", "adopting")


def test_adopt_promote_with_no_base_judges_against_the_base_branch(tmp_path: Path) -> None:
    # A local promotion is judged against `refs/remotes/origin/<project.base_branch>`. The
    # fixture has no remote-tracking ref, so `plan` cannot resolve that base and stays advisory;
    # once the ref exists at the first commit, the same call promotes it. Mutation: defaulting
    # to a ref other than the base branch's -> the second call exits 1.
    root, base = _project(tmp_path)
    code, out, _ = _cli(root, tmp_path, "adopt", "promote", "plan", "--json")
    assert code == 1
    assert json.loads(out)["promoted"] == []
    branch = _config(root, tmp_path).project.base_branch
    git(root, "update-ref", f"refs/remotes/origin/{branch}", base)
    code, out, err = _cli(root, tmp_path, "adopt", "promote", "plan", "--json")
    assert code == 0, err
    assert json.loads(out)["promoted"] == ["plan"]


def test_adopt_begin_prints_no_path_and_exits_2_on_a_plan_that_is_not_one(tmp_path: Path) -> None:
    # The plan's path is caller input, and a refusal names the rule rather than echoing it.
    root, _ = _project(tmp_path)
    stray = root / "2026-09-24-keelline-adoption.md"
    stray.write_text(PLAN, encoding="utf-8")
    code, out, err = _cli(root, tmp_path, "adopt", "begin", str(stray))
    assert code == 2
    assert "adoption plan" in err
    assert str(stray) not in out + err


def test_a_gate_that_could_not_run_is_named_and_the_command_exits_1(tmp_path: Path) -> None:
    # A custom gate whose command cannot start stays advisory, is named as one that could not
    # run, and nothing is written. Mutation: the unanswered names left out of `advisory` in
    # `run_adopt_promote` -> the summary loses the name and the command exits 0.
    root, base = _project(tmp_path)
    with (root / CONFIG_FILE).open("a", encoding="utf-8") as stream:
        stream.write('\n[gates.custom.absent]\nrun = ["keelline-test-no-such-command"]\n')
    before = _document(root)
    code, out, err = _cli(root, tmp_path, "adopt", "promote", "absent", "--base", base)
    assert code == 1, err
    assert out.strip() == (
        "promoted: nothing; still advisory: absent (could not run); state initialised"
    )
    assert _document(root) == before


def test_upgrade_after_a_promotion_plans_nothing_new(tmp_path: Path) -> None:
    # The two verbs move `state` and `enforced` and nothing `upgrade` owns, so `upgrade` moves
    # no key afterwards and plans what it planned before the adoption (the roadmap `docs trail`
    # rewrote is hand-edited to it) and nothing more. Mutation: the promotion's write also
    # setting `[keelline] version` to an older release -> `upgrade` plans to move it back.
    # Skipping the record's re-stamp does not redden this case, because `upgrade` never plans
    # `keelline.toml` itself; `test_uninstall_after_a_promotion_takes_keelline_toml_back` holds
    # the re-stamp.
    root, base = _project(tmp_path)

    def planned() -> list[tuple[str, str, str]]:
        report = upgrade(
            root, machine=tmp_path / "m.toml", runner=LsRemote(), dry_run=True, force=()
        )
        assert report.moved == ()
        assert not report.refused
        return [(a.artifact_id, str(a.verb), a.target) for a in report.footprint.actions]

    before = planned()
    begin(root, _config(root, tmp_path), root / ADOPTION)
    promote(root, _config(root, tmp_path), ["docs"], base=base)
    promote(root, _config(root, tmp_path), [], base=base)
    assert _config(root, tmp_path).keelline.state == "installed"
    assert planned() == before


def test_uninstall_after_a_promotion_takes_keelline_toml_back(tmp_path: Path) -> None:
    # The record was re-stamped at each write, so the promoted document is still one Keelline
    # wrote. Mutation: skipping `rewrite_owned`'s re-stamp -> `uninstall` keeps the file.
    root, base = _project(tmp_path)
    begin(root, _config(root, tmp_path), root / ADOPTION)
    promote(root, _config(root, tmp_path), [], base=base)
    code, _, err = _cli(root, tmp_path, "uninstall")
    assert code == 0, err
    assert not (root / CONFIG_FILE).exists()
