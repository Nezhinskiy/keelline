"""The oracle's own guards, which nothing exercised.

`scripts/mutation_oracle.py` is the mechanism this project's strongest test convention rests
on — "every new assertion ships with the mutation that reddens it" — and it had no tests of its
own, so the two states it could not tell apart were invisible by construction: a mutation whose
named tests do not exist read as *caught*, and a `git status` that could not answer read as a
*clean tree*. Both are proved here, against a real pytest run and a real repository.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mutation_oracle.py"
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def oracle(root: Path | None = None) -> ModuleType:
    """The script, loaded by path because `scripts/` is not an importable package.

    Registered in `sys.modules` before it is executed: `@dataclass` resolves a field's
    annotations through `sys.modules[cls.__module__]`, and a module absent from there makes
    the decorator raise on `Mutation` itself.

    `root` redirects the module's `ROOT`, which is where it runs pytest and asks `git` about
    the tree. Every test below points it at a throwaway directory, so nothing here mutates a
    file in this checkout or reads its git state.
    """
    name = "mutation_oracle_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    if root is not None:
        # Through `__dict__`, not an attribute assignment: `ModuleType` types reads as
        # `Any` and writes as an error, and this one is deliberate.
        module.__dict__["ROOT"] = root
    return module


def a_mutation(module: ModuleType, subject: Path, reddens: tuple[str, ...]) -> object:
    return module.Mutation(
        name="probe",
        file=subject,
        before="GUARD = True",
        after="GUARD = False",
        reddens=reddens,
    )


# --- the clean-tree run, which is what tells a proof from a typo -----------------------------
#
# `_check` mutates, runs the named tests, and reads "they did not pass" as "the mutation was
# caught". Without a clean-tree run first it cannot tell a red test from an absent one: a
# mistyped id makes pytest exit 4, 4 is not 0, and the oracle printed `caught` for a guard it
# had never tested. Measured before the fix, against this tree: `_check` returned `None`.


def test_a_test_id_that_does_not_exist_is_a_finding_not_a_catch(tmp_path: Path) -> None:
    module = oracle(root=tmp_path)
    subject = tmp_path / "subject.py"
    subject.write_text("GUARD = True\n", encoding="utf-8")
    finding = module._check(
        a_mutation(module, subject, ("test_nothing.py::test_this_name_does_not_exist",)), tmp_path
    )
    assert finding is not None
    assert "did not pass on a clean tree" in finding
    # Untouched: the run stopped before the write, so a bad entry cannot even risk the restore.
    assert subject.read_text(encoding="utf-8") == "GUARD = True\n"


def test_a_run_where_every_named_test_skipped_proves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The same hole wearing a different face, and one an environment produces rather than a
    # typo: this suite has nine environmental skips (no `git`, running as root, no interpreter
    # below the floor). A run of zero executed tests exits 0, so an exit code alone reads it as
    # a clean pass and banks the skip as a proof. Substituted at `_run`, the subprocess
    # boundary, because a skip that is reliably a skip on every CI leg is not something a test
    # can arrange honestly.
    module = oracle(root=tmp_path)
    subject = tmp_path / "subject.py"
    subject.write_text("GUARD = True\n", encoding="utf-8")
    monkeypatch.setattr(module, "_run", lambda _targets, _cwd: module.Outcome(code=0, executed=0))
    finding = module._check(
        a_mutation(module, subject, ("test_x.py::test_skipped_here",)), tmp_path
    )
    assert finding is not None
    assert "0 test(s) ran" in finding


def test_a_real_guard_with_a_real_test_is_still_reported_caught(tmp_path: Path) -> None:
    # The refusals above prove the oracle can say no; this proves the no is not simply always.
    # A guard, a test that depends on it, and a mutation that breaks it, end to end through a
    # real pytest run in a throwaway tree.
    module = oracle(root=tmp_path)
    subject = tmp_path / "subject.py"
    subject.write_text("GUARD = True\n", encoding="utf-8")
    (tmp_path / "test_subject.py").write_text(
        "import subject\n\n\ndef test_the_guard_holds() -> None:\n    assert subject.GUARD\n",
        encoding="utf-8",
    )
    caught = module._check(
        a_mutation(module, subject, ("test_subject.py::test_the_guard_holds",)), tmp_path
    )
    assert caught is None  # `None` is this function's word for "the mutation was caught"
    assert subject.read_text(encoding="utf-8") == "GUARD = True\n"


def test_a_mutation_that_breaks_collection_is_a_finding_and_not_a_catch(tmp_path: Path) -> None:
    """The clean run's own argument, applied to the mutated run.

    `_check` gates the clean run on `Outcome.passed` — `code == 0 and executed > 0` — with a
    long paragraph about why an exit code alone cannot tell a green assertion from an absent
    one. It then judged the *mutated* run by `mutated.code` alone, computing `mutated.executed`
    and throwing it away. A mutation that makes the module unimportable exits 2 from a
    collection error, 2 is not 0, and that read as `caught`.

    Measured before the fix, with this exact fixture::

        caught   probe
        all 1 mutations were caught

    exit 0 — for an entry whose named test never ran. The module's own sentence is "an oracle
    whose own failures look exactly like its successes is worse than no oracle", and this is
    the half of it that was left open in a file of 368 entries.

    Mutation (declared): the `mutated.executed == 0` test is removed -> this reddens.
    """
    module = oracle(root=tmp_path)
    subject = tmp_path / "subject.py"
    subject.write_text("GUARD = True\n", encoding="utf-8")
    (tmp_path / "test_subject.py").write_text(
        "import subject\n\n\ndef test_the_guard_holds() -> None:\n    assert subject.GUARD\n",
        encoding="utf-8",
    )
    breaks_the_import = module.Mutation(
        name="probe",
        file=subject,
        before="GUARD = True",
        after="import a_module_that_does_not_exist\nGUARD = True",
        reddens=("test_subject.py::test_the_guard_holds",),
    )
    finding = module._check(breaks_the_import, tmp_path)
    assert finding is not None, "a collection error read as the guard being caught"
    assert "from running at all" in finding, finding
    # Both counts in the message, so a reader can tell this from a guard that legitimately
    # stops a parametrised case being generated.
    assert "1 test(s) ran on the clean tree, 0 with the mutation applied" in finding, finding
    assert subject.read_text(encoding="utf-8") == "GUARD = True\n"


@needs_git
def test_a_leaked_scratch_checkout_is_swept_where_git_worktree_prune_will_not_take_it(
    tmp_path: Path,
) -> None:
    """The leak, and the reason `prune` was never going to clear it.

    `scratch_checkout`'s docstring promised that an interrupted run "leaves nothing behind but
    a prunable entry, which the next `git worktree prune` clears". Both halves were false: the
    `mkdtemp` tree is still on disk, and `prune` only drops entries whose directory is *gone*.
    One such registration was live in the development repository at review time — 6.5 MB, and
    `git worktree prune --dry-run -v` printed nothing about it — pinning a commit against
    `git gc` and joining `hooks/run-hook.sh`'s `list_checkouts` containment set.

    This builds a real repository, registers a leak under the real prefix, and asserts that
    `prune` declines it and the sweep takes it.

    Mutation (declared): the sweep's `worktree remove` is dropped -> the entry survives and
    this reddens.
    """
    import subprocess

    env = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    repository = tmp_path / "repo"
    repository.mkdir()
    git("init", "-q", "-b", "main")
    (repository / "a.txt").write_text("a\n", encoding="utf-8")
    git("add", "-A")
    git("-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "chore: one")

    module = oracle(root=repository)
    leaked = tmp_path / f"{module.SCRATCH_PREFIX}leaked-by-a-kill"
    tree = leaked / "tree"
    git("worktree", "add", "--detach", "--quiet", str(tree), "HEAD")
    assert tree.is_dir()
    # The premise, measured rather than assumed: prune leaves it exactly where it is.
    git("worktree", "prune")
    assert str(tree) in git("worktree", "list").stdout, "prune took it, so there is no leak"

    dropped = module.sweep_stale_scratch()
    assert str(leaked) in dropped, dropped
    assert str(tree) not in git("worktree", "list").stdout, git("worktree", "list").stdout
    assert not leaked.exists(), sorted(tmp_path.iterdir())


def test_a_mutation_nothing_notices_is_reported_as_surviving(tmp_path: Path) -> None:
    # And the finding the oracle exists to produce: the named test passes on a clean tree and
    # passes again with the guard broken. Without the clean-tree run this and the typo above
    # were told apart by nothing at all.
    module = oracle(root=tmp_path)
    subject = tmp_path / "subject.py"
    subject.write_text("GUARD = True\n", encoding="utf-8")
    (tmp_path / "test_subject.py").write_text(
        "import subject\n\n\ndef test_the_guard_holds() -> None:\n"
        "    assert subject.GUARD in (True, False)\n",
        encoding="utf-8",
    )
    finding = module._check(
        a_mutation(module, subject, ("test_subject.py::test_the_guard_holds",)), tmp_path
    )
    assert finding is not None
    assert finding.startswith("survived")


# --- the dirty-tree guard, which must not stand down when `git` cannot answer ----------------
#
# The guard exists because this script writes source files and restores them from memory; its
# own comment says "refuse rather than risk it". It read any non-zero `git` exit as a clean
# tree — and `git status` exits 128 outside a repository, which is exactly what an unpacked
# sdist is (`scripts/**` and `mutations.toml` ship in it) and what a broken `git` produces.


@needs_git
def test_a_tree_git_cannot_answer_about_is_refused_not_assumed_clean(tmp_path: Path) -> None:
    module = oracle(root=tmp_path)  # not a repository: `git status` exits 128 here
    subject = tmp_path / "subject.py"
    subject.write_text("GUARD = True\n", encoding="utf-8")
    refusal = module._uncommitted({subject})
    assert refusal is not None
    assert "could not answer" in refusal


@needs_git
def test_a_committed_tree_is_not_refused_and_a_dirty_one_still_is(tmp_path: Path) -> None:
    # The other side of the same guard. A refusal that fired on everything would be no guard
    # either — it would make the oracle unrunnable rather than fail-closed — and the original
    # behaviour it replaces has to survive intact.
    module = oracle(root=tmp_path)
    subject = tmp_path / "subject.py"
    subject.write_text("GUARD = True\n", encoding="utf-8")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")
    assert module._uncommitted({subject}) is None
    subject.write_text("GUARD = False\n", encoding="utf-8")
    refusal = module._uncommitted({subject})
    assert refusal is not None
    assert "uncommitted changes" in refusal


def test_a_git_that_cannot_be_launched_is_refused_not_assumed_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A `git` that is absent rather than unhappy raises out of `subprocess.run` instead of
    # returning non-zero, so the exit-code arm above never sees it. Uncaught it is a traceback;
    # read as "clean" it is the same fail-open. Neither.
    module = oracle(root=tmp_path)

    def _absent(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("git")

    monkeypatch.setattr(module.subprocess, "run", _absent)
    refusal = module._uncommitted({tmp_path / "subject.py"})
    assert refusal is not None
    assert "could not be run" in refusal


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        },
    )


# --- the scratch checkout, which is why the working tree is never written --------------------


def _repo_with_guard(root: Path) -> None:
    """A committed repository with one guard and one test that imports it.

    The test records the path it ran from into `ORACLE_PROBE`, which is how the outer test
    learns whether pytest was collected from the scratch checkout or from this repository.
    """
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "pkg" / "guard.py").write_text("GUARD = True\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_guard.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "from pkg.guard import GUARD\n"
        "\n"
        "\n"
        "def test_the_guard_holds() -> None:\n"
        "    Path(os.environ['ORACLE_PROBE']).write_text(__file__, encoding='utf-8')\n"
        "    assert GUARD\n",
        encoding="utf-8",
    )
    (root / "mutations.toml").write_text(
        "[[mutation]]\n"
        'name = "the guard is disarmed"\n'
        'file = "src/pkg/guard.py"\n'
        'before = "GUARD = True"\n'
        'after = "GUARD = False"\n'
        'reddens = ["tests/test_guard.py::test_the_guard_holds"]\n',
        encoding="utf-8",
    )
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=a@b.c", "-c", "user.name=a", "commit", "-qm", "init")


@needs_git
def test_the_working_tree_is_never_written_and_pytest_runs_in_the_scratch_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # DC1, and the retrospective's A3: the oracle used to rewrite `mutation.file` in place and
    # restore it from a string held in memory, so two runs at once interleaved writes over one
    # file. It now applies every mutation to a detached worktree of HEAD. Proved from both
    # sides: every byte of the repository is identical before and after, and the fixture test
    # reports that it was collected from somewhere that is not this repository.
    #
    # Mutation (declared): `_run`'s `cwd=cwd` back to `cwd=ROOT` -> pytest is collected from
    # the repository, the probe path lands under `tmp_path`, and the second assertion reddens.
    root = tmp_path / "repo"
    root.mkdir()
    _repo_with_guard(root)
    module = oracle(root=root)
    module.__dict__["DECLARATION"] = root / "mutations.toml"
    probe = tmp_path / "probe.txt"
    monkeypatch.setenv("ORACLE_PROBE", str(probe))
    before = {path: path.read_bytes() for path in root.rglob("*.py")}
    assert before  # a walk-based assertion states its walk is non-empty: `{} == {}` passes
    assert module.main([]) == 0
    assert {path: path.read_bytes() for path in root.rglob("*.py")} == before
    ran_from = Path(probe.read_text(encoding="utf-8")).resolve()
    assert root.resolve() not in ran_from.parents, ran_from


@needs_git
def test_the_scratch_copy_wins_over_a_main_checkout_already_on_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The editable install of the real repository puts its `src/` on `sys.path` through
    # site-packages, so a scratch checkout whose `src/` is not put *first* runs the named tests
    # against the unmutated main modules and reports every mutation as surviving. Modelled by
    # putting the repository's own `src` on PYTHONPATH before the run: only a prepend of the
    # scratch `src` makes the mutated copy the one imported.
    #
    # Mutation (declared): drop the PYTHONPATH prepend in `_run` -> the mutation survives,
    # `main` returns 1, and the assertion reddens.
    root = tmp_path / "repo"
    root.mkdir()
    _repo_with_guard(root)
    module = oracle(root=root)
    module.__dict__["DECLARATION"] = root / "mutations.toml"
    monkeypatch.setenv("ORACLE_PROBE", str(tmp_path / "probe.txt"))
    monkeypatch.setenv("PYTHONPATH", str(root / "src"))
    assert module.main([]) == 0


@needs_git
def test_a_scratch_checkout_that_cannot_be_created_is_a_refusal_not_an_in_place_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # No fallback to the old in-place behaviour: an oracle that silently mutated the working
    # tree because `git worktree add` failed would reintroduce the exact hazard DC1 removes.
    # `subprocess.run` is wrapped so that only the worktree call fails; `git status` and pytest
    # are real.
    #
    # No mutation entry of its own: the in-place fallback is a code path this module no
    # longer has, so there is no line to substitute. Measured by hand instead — making
    # `scratch_checkout` yield `ROOT` on failure reddens the first assertion below with
    # `assert 0 == 1`, because the fallback run mutates the fixture repository in place, the
    # entry is caught there, and `main` returns 0. The later two assertions are not reached:
    # the first `assert` ends the test, which is why this says "the first" and not "both".
    root = tmp_path / "repo"
    root.mkdir()
    _repo_with_guard(root)
    module = oracle(root=root)
    module.__dict__["DECLARATION"] = root / "mutations.toml"
    monkeypatch.setenv("ORACLE_PROBE", str(tmp_path / "probe.txt"))
    real_run = module.subprocess.run

    def _no_worktree(argv: list[str], *args: object, **kwargs: object) -> object:
        if "worktree" in argv:
            return subprocess.CompletedProcess(argv, 128, "", "fatal: no worktree today")
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", _no_worktree)
    assert module.main([]) == 1
    assert "worktree" in capsys.readouterr().err
    assert (root / "src" / "pkg" / "guard.py").read_text(encoding="utf-8") == "GUARD = True\n"


@needs_git
def test_an_uncommitted_reddens_test_file_is_refused_like_an_uncommitted_source_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The dirty-tree guard's second arm, which the scratch checkout is what makes it necessary:
    # a HEAD checkout cannot see an uncommitted edit to a *test* any more than to a source, so
    # an entry whose `reddens` file is dirty would be proved against the committed test while
    # its author reads the result as being about the one on screen. `main` therefore sweeps the
    # `reddens` files as well as the mutated ones. Only the test file is dirty here.
    #
    # Mutation (declared): drop the `reddens` files from the set `main` sweeps -> the run is
    # not refused, `main` returns 0, and the first assertion reddens.
    root = tmp_path / "repo"
    root.mkdir()
    _repo_with_guard(root)
    module = oracle(root=root)
    module.__dict__["DECLARATION"] = root / "mutations.toml"
    (root / "tests" / "test_guard.py").write_text(
        "def test_the_guard_holds() -> None:\n    pass\n", encoding="utf-8"
    )
    assert module.main([]) == 1
    assert "uncommitted changes" in capsys.readouterr().err
