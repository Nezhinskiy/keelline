"""The guards on the one fixture `git`, and on there going on being only one of it.

Twenty-three modules each carried a copy, and the copies were protected by five different
subsets of the same precaution. Collapsing them is only half the repair: the other half is that
the twenty-fourth copy cannot be written without a test going red, which is what the walk at
the bottom of this file is for.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from tests.gitfixture import ENV_KEEP, env, git, needs_git, run_git

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

# What points `git` at a repository other than the one it was handed. `keelline.runner` names
# the same seven as the set it drops, and its docstring says why each is there; this list is
# that one, and a variable added there belongs here too.
REDIRECTING = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
)

# The one `git` in the suite that this module does not run, named rather than skipped silently
# — for `tests/test_areas.py`'s stated reason, that an exemption nobody can see is how the
# violation a guard exists to catch gets merged green. `tracked_files` asks the *real*
# repository which files it tracks, reads the answer as bytes because `-z` separates with NUL,
# and is the neutrality gate's own enumeration rather than a fixture being built.
HAND_ROLLED_EXEMPT = frozenset({("test_neutral.py", "tracked_files")})

# The shared fixture and the module you are reading, which are the two that may name the
# variables the rest of the suite must not spell for itself.
_THE_FIXTURE_AND_ITS_GUARD = frozenset({"gitfixture.py", "test_gitfixture.py"})


@needs_git
def test_a_fixture_repository_is_built_where_it_was_asked_although_git_dir_names_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The defect the sealed environment exists to close, and the reason it matters more here
    # than in `keelline.gitenv`: these calls are `init`, `add` and `commit`, so an inherited
    # `GIT_DIR` does not make a fixture read the wrong repository, it makes it *write* to one.
    # Under `pytest -p xdist` or a shell that exports `GIT_DIR`, that repository is whichever
    # one the developer is sitting in.
    #
    # Mutation (declared): `env()` returns `dict(os.environ)` -> `git init` reinitialises the
    # victim, the commit lands there, and both assertions below fail.
    victim = tmp_path / "victim"
    victim.mkdir()
    git(victim, "init", "-q", "-b", "main")
    monkeypatch.setenv("GIT_DIR", str(victim / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(victim))

    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q", "-b", "main")
    (project / "a.txt").write_text("a\n", encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "chore: seed")

    # The specific sentence and not "something went wrong": the commit is in the repository
    # that was named, under the forced identity, and the victim never got one.
    assert git(project, "log", "-1", "--format=%s").strip() == "chore: seed"
    assert git(project, "log", "-1", "--format=%ae").strip() == "t@example.com"
    assert run_git(victim, "rev-parse", "HEAD").returncode != 0


def test_the_sealed_environment_carries_nothing_that_could_redirect_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mutation (declared): the same one — `dict(os.environ)` carries all seven through.
    for name in REDIRECTING:
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    # Asserted present in the ambient environment before they are asserted absent from the
    # sealed one: a `REDIRECTING` that had been emptied, or a `monkeypatch` that stopped
    # setting anything, would satisfy the subtraction below having compared nothing.
    assert set(REDIRECTING) <= set(os.environ)

    sealed = env(tmp_path)
    assert set(REDIRECTING) & set(sealed) == set()
    # And the keep-list is an allowlist rather than a denylist, which is why adding an eighth
    # redirecting variable to git needs no edit here: nothing survives that is not named.
    assert set(sealed) - set(ENV_KEEP) == {
        "HOME",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_TERMINAL_PROMPT",
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
    }
    assert sealed["HOME"] == str(tmp_path)


def _git_runs(tree: ast.AST) -> list[int]:
    """Every `…run(["git", …], …)` in this module, by line."""
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        first = node.args[0]
        if name != "run" or not isinstance(first, ast.List) or not first.elts:
            continue
        head = first.elts[0]
        if isinstance(head, ast.Constant) and head.value == "git":
            found.append(node.lineno)
    return found


def _enclosing(tree: ast.AST, line: int) -> str:
    """The innermost `def` a line sits in, so an exemption names a function and not a number."""
    best = ("<module>", -1)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.lineno <= line <= (node.end_lineno or node.lineno)
            and node.lineno > best[1]
        ):
            best = (node.name, node.lineno)
    return best[0]


def test_no_test_module_runs_a_git_of_its_own() -> None:
    # The durable half of the collapse. Twenty-three named helpers and six further inline call
    # sites each built the environment by hand, and nothing held any of them to any other — so
    # `os.devnull` had drifted to the literal `"/dev/null"` on twelve lines, four sites never
    # set `GIT_TERMINAL_PROMPT`, and three ran `git init` with no environment at all. A
    # twenty-fourth copy would have arrived the same way: unremarked.
    #
    # Mutation (declared): the walk is narrowed to `gitfixture.py`, which this module excludes
    # -> `modules` comes back empty and the floor below reddens, because a guard that stopped
    # walking reports no offences for the same reason a clean tree does.
    modules = sorted(p for p in TESTS.rglob("*.py") if p.name != "gitfixture.py")
    assert len(modules) >= 90, len(modules)
    offences: list[str] = []
    for path in modules:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line in _git_runs(tree):
            where = (path.name, _enclosing(tree, line))
            if where not in HAND_ROLLED_EXEMPT:
                offences.append(f"{path.relative_to(ROOT)}:{line} runs git without gitfixture")
    assert not offences, "\n".join(offences)


def test_no_test_module_builds_a_git_environment_of_its_own() -> None:
    # The other spelling of the same defect, and the one that catches a hand-built environment
    # handed to something that is not `subprocess.run` — the two `env=` dictionaries that were
    # passed to a launcher rather than to git. String constants out of the AST rather than a
    # substring search, so the prose in `tests/snapshot.py` that *describes* the precaution is
    # not mistaken for a second copy of it. This module is excluded beside `gitfixture.py` and
    # for the same reason: the assertion above spells the eight forced names out, so that
    # dropping one from `gitfixture.env` reddens rather than passing quietly.
    #
    # No separate mutation: the walk is the one above's, and narrowing it reddens there first.
    modules = sorted(p for p in TESTS.rglob("*.py") if p.name not in _THE_FIXTURE_AND_ITS_GUARD)
    assert len(modules) >= 90, len(modules)
    named = {
        str(path.relative_to(ROOT))
        for path in modules
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant)
        and node.value in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")
    }
    assert named == set(), named
