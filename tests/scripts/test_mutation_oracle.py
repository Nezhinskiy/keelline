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
        a_mutation(module, subject, ("test_nothing.py::test_this_name_does_not_exist",))
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
    monkeypatch.setattr(module, "_run", lambda _targets: module.Outcome(code=0, executed=0))
    finding = module._check(a_mutation(module, subject, ("test_x.py::test_skipped_here",)))
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
    caught = module._check(a_mutation(module, subject, ("test_subject.py::test_the_guard_holds",)))
    assert caught is None  # `None` is this function's word for "the mutation was caught"
    assert subject.read_text(encoding="utf-8") == "GUARD = True\n"


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
    finding = module._check(a_mutation(module, subject, ("test_subject.py::test_the_guard_holds",)))
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
