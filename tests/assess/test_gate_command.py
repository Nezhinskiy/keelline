"""`keelline gate` through the real parser, over a real clone: the verdict a pull request faces.

Every case commits its edit, because CI checks out a committed head, except the one that asks
about an uncommitted loosening on purpose. A refusal, a failure and an internal error all print
on standard error, so every case that must not quote a name reads both streams.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

import keelline
from keelline.assess import rule
from keelline.assess.report import BOOTSTRAP, FINDINGS_ELSEWHERE
from keelline.cli import build_parser, discover_registrars, run
from keelline.config.loader import CONFIG_FILE
from tests.assess.baserepo import AGENTS, clone, commit
from tests.gitfixture import git, needs_git

pytestmark = needs_git

BASE = f"""[keelline]
version = "{keelline.__version__}"
state = "adopting"
enforced = ["docs"]

[project]
name = "widget"
"""
LOOSENED = BASE.replace('["docs"]', "[]")
BUILTINS = ["docs", "bugs", "plan", "commit", "trail"]
SHA = "b" * 40
# Well past the preset's `AGENTS.md` budget, so the `docs` gate has a finding.
OVER_BUDGET = "".join("word\n" for _ in range(400))
NOTHING_TO_RUN = "nothing to run: no configured gate of the kind asked for"


def _custom(name: str, code: str) -> str:
    """A `[gates.custom.<name>]` table running `code` under this interpreter."""
    argv = json.dumps([sys.executable, "-c", code])
    return f"\n[gates.custom.{name}]\nrun = {argv}\n"


MARKER = _custom("tests", "open('marker', 'w').close()")


def _gate(root: Path, tmp_path: Path, *argv: str) -> tuple[int, str, str]:
    parser = build_parser(discover_registrars())
    args = ["gate", "--root", str(root), "--machine", str(tmp_path / "absent.toml"), *argv]
    with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
        code = run(args, parser=parser)
    return code, out.getvalue(), err.getvalue()


def _heads(out: str) -> list[str]:
    return [line.split(":", 1)[0] for line in out.splitlines()]


def _change(project: Path, text: str, *, agents: str | None = None) -> None:
    """Commit `text` as the tree's `keelline.toml`, and `agents` as its `AGENTS.md`."""
    (project / CONFIG_FILE).write_text(text, encoding="utf-8")
    if agents is not None:
        (project / "AGENTS.md").write_text(agents, encoding="utf-8")
    commit(project, "chore: the change under review")


def test_a_loosening_change_fails_the_configuration_check(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    _change(project, LOOSENED)
    code, out, _ = _gate(project, tmp_path, "--only", "config")
    assert code == 1
    assert "keelline.enforced" in out


def test_the_bare_command_judges_the_configuration_and_runs_every_configured_gate(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE)
    code, out, _ = _gate(project, tmp_path)
    assert code == 0, out
    assert _heads(out) == ["config", *BUILTINS]


def test_json_carries_the_verdict_and_each_gate_s_count_and_no_finding(tmp_path: Path) -> None:
    # Advice: the shape `docs/cli.md` promises. Mutation: drop `"refused"` from the `config`
    # object -> the key comparison reddens.
    project = clone(tmp_path, BASE)
    _change(project, LOOSENED)
    code, out, _ = _gate(project, tmp_path, "--only", "config", "--only", "docs", "--json")
    assert code == 1
    printed = json.loads(out)
    assert set(printed["config"]) == {"judged", "base_state", "changes", "refused", "enforcing"}
    assert printed["config"]["changes"] == [{"key": "keelline.enforced", "verdict": "refused"}]
    assert printed["config"]["refused"] is True
    assert printed["gates"] == [{"name": "docs", "enforcing": True, "answered": True, "count": 0}]


def test_an_enforced_custom_gate_runs_its_command_and_fails_on_its_exit_status(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE)
    tree = BASE.replace('["docs"]', '["docs", "tests"]') + _custom("tests", "raise SystemExit(3)")
    _change(project, tree)
    code, out, _ = _gate(project, tmp_path)
    assert code == 1
    assert "tests: enforcing, 1 finding(s)" in out.splitlines()


def test_a_built_in_gate_added_under_installed_enforces_in_the_run_that_adds_it(
    tmp_path: Path,
) -> None:
    # Under `installed` every gate the project runs enforces, so the pull request that adds a
    # built-in gate is held to it at once: the enforcing set is the base's and the tree's.
    # Mutation: `judge` enforcing the base's set alone (declared against the rule's own tests)
    # -> `docs` is advisory here and the run passes.
    installed = BASE.replace('state = "adopting"\nenforced = ["docs"]\n', 'state = "installed"\n')
    project = clone(tmp_path, installed + '\n[gates]\nbuiltin = ["bugs"]\n')
    _change(project, installed + '\n[gates]\nbuiltin = ["docs", "bugs"]\n', agents=OVER_BUDGET)
    code, out, _ = _gate(project, tmp_path)
    assert code == 1
    lines = out.splitlines()
    assert lines[0] == "config: 2 change(s), 0 refused"
    # The 400-line `AGENTS.md` breaks two budgets; "could not run" would not be this line.
    assert lines[1] == "docs: enforcing, 2 finding(s)"


def test_builtin_runs_no_command_the_repository_wrote_and_custom_runs_only_those(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE)
    _change(project, BASE + MARKER)
    code, out, _ = _gate(project, tmp_path, "--builtin")
    assert code == 0, out
    assert not (project / "marker").exists()
    assert _heads(out) == ["config", *BUILTINS]
    code, out, _ = _gate(project, tmp_path, "--custom")
    assert code == 0, out
    assert (project / "marker").exists()
    assert _heads(out) == ["tests"]


def test_custom_alone_leaves_the_verdict_to_the_judging_run(tmp_path: Path) -> None:
    # The judging run refuses this change and the workflow never reaches the custom step; run by
    # hand, `--custom` reports the gates and nothing else. No mutation: counting the refusal here
    # would only fail a run that already failed.
    passing = _custom("tests", "pass")
    project = clone(tmp_path, BASE + passing)
    _change(project, LOOSENED + passing)
    code, out, _ = _gate(project, tmp_path, "--custom")
    assert code == 0, out
    assert _heads(out) == ["tests"]


def test_custom_on_a_project_with_no_custom_gate_exits_zero(tmp_path: Path) -> None:
    # The reusable workflow runs `--custom` on every caller, most of which configure no gate of
    # their own. Mutation (advice): `raise Refusal(NOTHING_TO_RUN)` in place of the `Result` ->
    # exit 2, and every such project's pull requests fail.
    project = clone(tmp_path, BASE)
    code, out, _ = _gate(project, tmp_path, "--custom")
    assert (code, out.strip()) == (0, NOTHING_TO_RUN)


def test_builtin_skips_a_custom_gate_named_by_only(tmp_path: Path) -> None:
    # A matrix caller's `only:` may name a custom gate in the judging step: it is the next
    # step's to run, so it is skipped here, and nothing left to run is not a failure. Mutation
    # (advice): `raise Refusal(NOTHING_TO_RUN)` in place of the `Result` -> exit 2.
    project = clone(tmp_path, BASE)
    _change(project, BASE + MARKER)
    code, out, _ = _gate(project, tmp_path, "--builtin", "--only", "tests")
    assert (code, out.strip()) == (0, NOTHING_TO_RUN)
    assert not (project / "marker").exists()


def test_a_gate_only_the_refused_tree_defines_is_not_run_and_the_run_fails(
    tmp_path: Path,
) -> None:
    # A refused change runs under the base's configuration, and the enforcing set is still both
    # sides': here it names `tests`, which only the tree defines. The run neither runs the tree's
    # command nor trips over the name — it fails on the refusal. With the names to run read off
    # the tree, `run_gates` raises `KeyError('tests')`: exit 2, which this case catches, but the
    # same mutation makes the custom step of the dropped-gate case below pass with nothing run.
    project = clone(tmp_path, BASE)
    tree = BASE.replace('["docs"]', '["docs", "tests"]') + MARKER
    _change(project, tree + '\n[paths]\nbugs = "elsewhere"\n')
    code, out, err = _gate(project, tmp_path)
    assert code == 1, err
    assert out.splitlines()[0].endswith("refused: paths.bugs")
    assert _heads(out) == ["config", *BUILTINS, "details"]
    assert not (project / "marker").exists()


ENFORCES_TESTS = BASE.replace('["docs"]', '["docs", "tests"]')


def test_a_refused_change_runs_the_base_s_command_for_a_gate_the_base_enforces(
    tmp_path: Path,
) -> None:
    # A custom gate's command is fixed by the base while the base enforces it: the change that
    # re-commands it is refused, the judging step fails on that, and the custom step runs the
    # base's command, never the change's.
    project = clone(tmp_path, ENFORCES_TESTS + _custom("tests", "pass"))
    _change(project, ENFORCES_TESTS + MARKER)
    code, out, _ = _gate(project, tmp_path, "--builtin")
    assert code == 1
    assert out.splitlines()[0] == "config: 1 change(s), 1 refused: gates.custom.tests.run"
    assert _heads(out) == ["config", *BUILTINS, "details"]
    code, out, _ = _gate(project, tmp_path, "--custom")
    assert (code, out.strip()) == (0, "tests: enforcing, 0 finding(s)")
    assert not (project / "marker").exists()


def test_a_refused_change_is_checked_at_the_base_s_paths(tmp_path: Path) -> None:
    # A refused `[paths]` value does not move where the gates look: here the change points
    # `agents_md` at a small file and leaves the over-budget one where the base reads it.
    project = clone(tmp_path, BASE)
    (project / "NOTES.md").write_text(AGENTS, encoding="utf-8")
    _change(project, BASE + '\n[paths]\nagents_md = "NOTES.md"\n', agents=OVER_BUDGET)
    code, out, _ = _gate(project, tmp_path, "--only", "config", "--only", "docs")
    assert code == 1
    lines = out.splitlines()
    assert lines[0] == "config: 1 change(s), 1 refused: paths.agents_md"
    # The 400-line `AGENTS.md` breaks two budgets; "could not run" would not be this line.
    assert lines[1] == "docs: enforcing, 2 finding(s)"


def test_a_custom_gate_the_base_does_not_enforce_runs_its_new_command(tmp_path: Path) -> None:
    # The legitimate side of the two cases above: re-commanding a gate the base does not
    # enforce is neutral, so the run is the tree's and the new command is the one that runs.
    project = clone(tmp_path, BASE + _custom("tests", "pass"))
    _change(project, BASE + MARKER)
    code, out, _ = _gate(project, tmp_path, "--builtin")
    assert code == 0, out
    assert out.splitlines()[0] == "config: 1 change(s), 0 refused"
    assert not (project / "marker").exists()
    code, out, _ = _gate(project, tmp_path, "--custom")
    assert (code, out.strip()) == (0, "tests: advisory, 0 finding(s)")
    assert (project / "marker").exists()


def test_builtin_runs_no_custom_gate_the_base_keeps_when_the_change_drops_it(
    tmp_path: Path,
) -> None:
    # Which names are custom is the verdict's configuration's answer too: a change that drops
    # an enforced custom gate is refused and runs under the base's configuration, where the
    # gate still is. Read off the tree, the judging step would take it for a built-in and run
    # its command in the process that judges; and with the names to run read off the tree, the
    # custom step would find nothing to run and pass without running the gate the base enforces.
    project = clone(tmp_path, ENFORCES_TESTS + MARKER)
    _change(project, BASE)
    code, out, _ = _gate(project, tmp_path, "--builtin")
    assert code == 1
    assert out.splitlines()[0] == (
        "config: 2 change(s), 2 refused: gates.custom.tests.run, keelline.enforced"
    )
    assert _heads(out) == ["config", *BUILTINS, "details"]
    assert not (project / "marker").exists()
    code, out, _ = _gate(project, tmp_path, "--custom")
    assert (code, out.strip()) == (0, "tests: enforcing, 0 finding(s)")
    assert (project / "marker").exists()


def test_a_tree_without_keelline_toml_fails_and_names_the_file(tmp_path: Path) -> None:
    # `keelline uninstall` in a pull request: nothing says which gates run. Mutation (advice):
    # drop the `tree_text is None` check -> `loads(None)` is an internal error, exit 2, and the
    # exit code reddens. Not declared: exit 2 fails the run as well.
    project = clone(tmp_path, BASE)
    git(project, "rm", "-q", CONFIG_FILE)
    commit(project, "chore: uninstall")
    code, _, err = _gate(project, tmp_path)
    assert code == 1
    assert "no keelline.toml" in err


def test_a_symlinked_keelline_toml_is_refused(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    outside = tmp_path / "outside.toml"
    outside.write_text(BASE, encoding="utf-8")
    (project / CONFIG_FILE).unlink()
    (project / CONFIG_FILE).symlink_to(outside)
    commit(project, "chore: a linked configuration")
    summary = tmp_path / "summary.md"
    code, out, err = _gate(project, tmp_path, "--summary", str(summary))
    assert code == 2
    assert CONFIG_FILE in err
    assert out == ""
    assert not summary.exists()
    assert outside.read_text(encoding="utf-8") == BASE


def test_a_gate_the_base_does_not_enforce_passes_with_its_findings_reported(
    tmp_path: Path,
) -> None:
    plan = BASE.replace('["docs"]', '["plan"]')
    project = clone(tmp_path, plan)
    _change(project, plan, agents=OVER_BUDGET)
    code, out, _ = _gate(project, tmp_path, "--only", "docs")
    assert code == 0
    assert out.strip() == "docs: advisory, 2 finding(s)"


def test_the_enforced_gate_fails_on_its_findings(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    _change(project, BASE, agents=OVER_BUDGET)
    code, out, _ = _gate(project, tmp_path, "--only", "docs")
    assert code == 1
    assert out.splitlines()[0] == "docs: enforcing, 2 finding(s)"


def test_a_failing_run_ends_by_saying_where_the_findings_are(tmp_path: Path) -> None:
    # The printed lines are counts, and a first-time user had no pointer to the findings behind
    # them. One fixed line, and only on a run with a failing gate. Mutation (by hand): the line
    # dropped -> the last line is the gate's.
    project = clone(tmp_path, BASE)
    _change(project, BASE, agents=OVER_BUDGET)
    code, out, _ = _gate(project, tmp_path, "--only", "docs")
    assert code == 1
    assert out.splitlines() == ["docs: enforcing, 2 finding(s)", FINDINGS_ELSEWHERE]
    _change(project, BASE, agents=AGENTS)
    code, out, _ = _gate(project, tmp_path, "--only", "docs")
    assert (code, out.splitlines()) == (0, ["docs: enforcing, 0 finding(s)"])


def test_a_root_spelled_with_dot_dot_is_refused_for_what_it_is(tmp_path: Path) -> None:
    # `--root ..` from a subdirectory was refused with the symlink sentence, and nothing was
    # linked: `..` after a linked component is not the directory the spelling suggests, so the
    # refusal stays and says why. Mutation (by hand): the check removed -> the symlink sentence.
    project = clone(tmp_path, BASE)
    (project / "sub").mkdir()
    code, out, err = _gate(project / "sub" / "..", tmp_path, "--only", "config")
    assert (code, out) == (2, "")
    assert "`..`" in err and "symlink" not in err


def test_a_name_given_twice_runs_once(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    code, out, _ = _gate(project, tmp_path, "--only", "docs", "--only", "docs")
    assert code == 0
    assert _heads(out) == ["docs"]


def test_a_name_the_configuration_does_not_have_is_refused_and_not_quoted(
    tmp_path: Path,
) -> None:
    # The `--only` list is the caller workflow's, which a pull request can edit. Without the
    # check, `run_gates` raises `KeyError('tset')` and the frame's internal error quotes it on
    # standard error — which is why both streams are read.
    project = clone(tmp_path, BASE)
    code, out, err = _gate(project, tmp_path, "--only", "tset")
    assert code == 2
    assert "tset" not in out
    assert "tset" not in err
    assert "1 gate(s)" in err


def test_on_the_base_commit_the_tree_is_the_base(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    git(project, "checkout", "-q", "main")
    code, out, _ = _gate(project, tmp_path, "--only", "config")
    assert code == 0
    assert out.strip() == "config: keelline.toml unchanged from the base"


def test_an_uncommitted_loosening_on_the_base_commit_is_still_refused(tmp_path: Path) -> None:
    # Deliberately uncommitted: the tree is the working tree, never `HEAD`, so a checkout of the
    # base commit is not the base's copy by position alone.
    project = clone(tmp_path, BASE)
    git(project, "checkout", "-q", "main")
    (project / CONFIG_FILE).write_text(LOOSENED, encoding="utf-8")
    code, out, _ = _gate(project, tmp_path, "--only", "config")
    assert code == 1
    assert "keelline.enforced" in out


def test_a_base_with_no_copy_at_this_path_lets_the_tree_decide(tmp_path: Path) -> None:
    # The bootstrap, printed in the one spelling the job summary uses too.
    project = clone(tmp_path, BASE, under="sub")
    _change(project, BASE)
    code, out, _ = _gate(project, tmp_path, "--only", "config")
    assert (code, out.strip()) == (0, f"config: {BOOTSTRAP}")


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param(BASE + "\n[bogus]\nx = 1\n", id="unknown-section"),
        pytest.param(BASE + "\n[[broken\n", id="not-toml"),
    ],
)
def test_a_base_that_does_not_load_fails_the_run_and_names_the_base_s_copy(
    tmp_path: Path, broken: str
) -> None:
    # The base's copy governs the change, and one that does not load is never the bootstrap:
    # read as "no copy", the tree would decide its own configuration. The tree here is valid,
    # so a message naming the tree's file sends the owner to a file with nothing wrong in it.
    # Mutation (declared): the base's load failure answered as the bootstrap -> exit 0, and
    # every gate runs under the tree's configuration.
    project = clone(tmp_path, broken)
    _change(project, BASE)
    code, out, err = _gate(project, tmp_path)
    assert code == 1
    assert out == ""
    assert "the base's keelline.toml" in err
    assert str(project) not in err


def test_a_change_cannot_make_the_base_s_copy_fail_to_load_and_pass(tmp_path: Path) -> None:
    # Both sides load against the tree's disk, so a change can plant what the base's `[paths]`
    # then meets: a symlink on a path only the base names. The base's load refuses, and the
    # refusal fails the run rather than letting the tree judge itself. Mutation (by hand): the
    # base's load wrapped to answer any error as the bootstrap -> exit 0.
    moved = BASE + '\n[paths]\nroadmap = "elsewhere/roadmap.md"\n'
    project = clone(tmp_path, moved)
    (tmp_path / "target").mkdir()
    (project / "elsewhere").symlink_to(tmp_path / "target", target_is_directory=True)
    _change(project, BASE)
    code, out, err = _gate(project, tmp_path)
    assert code == 2
    assert out == ""
    assert "symlink" in err
    # Whose configuration met the link: the tree's `[paths]` does not name it. Mutation
    # (declared): the base's refusal passed through unwrapped -> the base is not named.
    assert "the base's keelline.toml" in err


def test_deleting_the_ledger_does_not_switch_an_enforced_bugs_gate_off(tmp_path: Path) -> None:
    # The base enforces `bugs` and has a ledger; the change deletes the ledger and cites an
    # entry file. "No ledger yet" was read off the tree the change wrote, and the gate reported
    # nothing. Mutation: the ledger's own entry (the uninitialised arm answering `[]`).
    enforced = BASE.replace('["docs"]', '["bugs"]')
    project = clone(tmp_path, enforced, also={"src.py": "# see docs/bugs/BR-001.md\n"})
    upstream = tmp_path / "upstream"
    bugs = upstream / "docs" / "bugs"
    bugs.mkdir(parents=True)
    (bugs / "BR-001.md").write_text(
        "---\nid: BR-001\ntitle: t\nstatus: open\nseverity: low\narea: a\nfound: 2026-01-01\n"
        "source:\nfixed_in:\nrelated:\n---\n\nbody\n",
        encoding="utf-8",
    )
    commit(upstream, "chore: a ledger")
    git(project, "fetch", "-q")
    git(project, "reset", "-q", "--hard", "origin/main")
    code, out, _ = _gate(project, tmp_path, "--builtin", "--only", "bugs")
    # With the ledger in place the citation resolves; the stale index is the one finding.
    assert (code, out.splitlines()[0]) == (1, "bugs: enforcing, 1 finding(s)")
    git(project, "rm", "-rq", "docs/bugs")
    commit(project, "chore: drop the ledger")
    code, out, _ = _gate(project, tmp_path, "--builtin", "--only", "bugs")
    assert code == 1
    assert out.splitlines()[0] == "bugs: enforcing, 1 finding(s)"


def test_a_base_branch_outside_its_grammar_is_named_and_never_blamed_on_base(
    tmp_path: Path,
) -> None:
    # With no `--base`, the default is `refs/remotes/origin/<base_branch>`, and a value outside
    # git's branch grammar was refused in `--base`'s words, a flag nobody passed. The loader
    # names the key now, and prints none of the value.
    project = clone(tmp_path, BASE)
    _change(project, BASE + 'base_branch = "main ::error::forged"\n')
    code, out, err = _gate(project, tmp_path)
    assert code == 1
    assert out == ""
    assert "project.base_branch is not a plain branch name" in err
    assert "--base" not in err and "forged" not in err


def test_a_base_the_checkout_lacks_fails_the_run_and_names_the_fix(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    code, _, err = _gate(project, tmp_path, "--base", "refs/remotes/origin/absent")
    assert code == 1
    assert "fetch-depth: 0" in err
    assert "refs/heads/main" in err  # the local remedy, for a clone with no origin


def test_an_unexpected_error_reading_the_base_is_never_the_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # "No copy on the base" lets the change decide its own configuration, so nothing reads a
    # failure as it: an error that is neither a failure nor a refusal is the frame's internal
    # error. Mutation (advice): `None` passed to `judge` in place of `read_base`'s answer, as a
    # handler that swallowed the error would -> the loosening is the bootstrap and exits 0.
    project = clone(tmp_path, BASE)
    _change(project, LOOSENED)

    def broken(root: Path, base: str) -> str | None:
        raise OSError("disk")

    monkeypatch.setattr(rule, "read_base", broken)
    code, _, err = _gate(project, tmp_path, "--only", "config")
    assert code == 2
    assert "internal error" in err


def test_a_short_base_name_is_refused_at_the_parser(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A tag spelled `origin/main` wins git's lookup of the short name. The parser's own error,
    # so it is read off the real standard error rather than through `_gate`.
    project = clone(tmp_path, BASE)
    parser = build_parser(discover_registrars())
    argv = ["gate", "--root", str(project), "--base", "origin/main"]
    with pytest.raises(SystemExit) as exited:
        run(argv, parser=parser)
    assert exited.value.code == 2
    assert "refs/" in capsys.readouterr().err


def test_a_project_in_a_subdirectory_is_annotated_from_the_repository_s_root(
    tmp_path: Path,
) -> None:
    project = clone(tmp_path, BASE, under="sub")
    _change(project / "sub", LOOSENED)
    code, out, _ = _gate(project / "sub", tmp_path, "--only", "config", "--annotate")
    assert code == 1
    assert "::error file=sub/keelline.toml::keelline.enforced may not change" in out


def test_what_prints_names_keys_and_rules_and_never_a_value_or_a_detail(tmp_path: Path) -> None:
    project = clone(tmp_path, BASE)
    tree = BASE + '\n[paths]\nbugs = "a-value-we-wrote"\n'
    _change(project, tree, agents="# widget\n\nSee [the notes](a-target-we-wrote.md).\n")
    summary = tmp_path / "summary.md"
    summary.write_text("an earlier step's summary\n", encoding="utf-8")
    code, out, _ = _gate(project, tmp_path, "--annotate", "--summary", str(summary))
    assert code == 1
    written = summary.read_text(encoding="utf-8")
    assert written.startswith("an earlier step's summary\n")
    for text in (out, written):
        assert "paths.bugs" in text
        assert "a-value-we-wrote" not in text
        assert "a-target-we-wrote" not in text
    assert "docs: missing-link" in out


def _upgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, released: bool) -> Path:
    """A base at an older Keelline pinned to one commit, and a change to the running one pinned
    to `SHA`, with the release tags answering `released` for every commit."""
    older = BASE.replace(f'"{keelline.__version__}"', '"0.0.1"')
    project = clone(tmp_path, older + f'\n[ci]\nref = "{"a" * 40}"\n')
    _change(project, BASE + f'\n[ci]\nref = "{SHA}"\n')
    monkeypatch.setattr("keelline.release.api.is_released", lambda sha, runner, *, cwd: released)
    return project


def test_an_upgrade_at_a_released_workflow_commit_passes_the_judging_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Dropping `workflow_sha=args.workflow_sha` refuses more, so it is not declared.
    project = _upgrade(tmp_path, monkeypatch, released=True)
    code, out, _ = _gate(project, tmp_path, "--only", "config", "--workflow-sha", SHA)
    assert code == 0, out
    assert out.strip() == "config: 2 change(s), 0 refused"


def test_an_upgrade_at_a_commit_no_release_names_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _upgrade(tmp_path, monkeypatch, released=False)
    code, out, _ = _gate(project, tmp_path, "--only", "config", "--workflow-sha", SHA)
    assert code == 1
    assert "ci.ref" in out


def test_a_local_run_without_the_workflow_sha_refuses_a_moved_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # On a branch `keelline upgrade` made, the moved pin is vouched for by nothing until
    # `--workflow-sha` names it, and `docs/cli.md` names that flag as the remedy.
    project = _upgrade(tmp_path, monkeypatch, released=True)
    code, out, _ = _gate(project, tmp_path, "--only", "config")
    assert code == 1
    assert "ci.ref" in out
