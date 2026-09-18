from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_launcher import _old_python

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "hooks" / "run-hook.sh"


def _plugin_root(
    base: Path, exit_code: int, *, echo_cwd: bool = False, with_launcher: bool = True
) -> Path:
    """A plugin root: a copy of the shipped wrapper, and a launcher beside it.

    The wrapper is **copied in** rather than invoked out of the checkout, because it now finds
    its launcher relative to its own path. A plugin root is therefore a real directory pair —
    `hooks/run-hook.sh` and `scripts/keelline` — which is what an installed plugin is, and what
    the harness substitutes into the command string of `hooks/hooks.json`.

    A fake launcher, not the real one: this test is about the wrapper's own exit-code mapping
    and its argv contract, and a real `keelline` run would couple it to every command in the
    package.

    Python and not `#!/bin/sh`, because the wrapper hands the launcher to the interpreter it
    probed — `"$p" "$launcher"` — rather than executing it by its shebang, which is the whole
    reason the probe exists: a launcher run by its own `#!/usr/bin/env python3` would be given
    whatever `python3` the session's PATH resolves to, which on macOS is 3.9. A shell script
    here therefore reaches Python as a `SyntaxError` and every exit code below arrives as 1.
    """
    root = base / "plugin"
    (root / "scripts").mkdir(parents=True)
    (root / "hooks").mkdir(parents=True)
    shutil.copy(WRAPPER, root / "hooks" / WRAPPER.name)
    (root / "hooks" / WRAPPER.name).chmod(0o755)
    if not with_launcher:
        return root
    launcher = root / "scripts" / "keelline"
    # `os.getcwd()` rather than the shell's `pwd`: it reports the physical directory, which is
    # what `Path.resolve()` names, so the assertion is about the directory and not about which
    # of its spellings the shell kept.
    body = "import os\n\nprint(os.getcwd())\n" if echo_cwd else ""
    launcher.write_text(
        f"#!/usr/bin/env python3\n{body}raise SystemExit({exit_code})\n", encoding="utf-8"
    )
    launcher.chmod(0o755)
    return root


def _run(
    *argv: str,
    plugin_root: Path,
    env_root: Path | None = None,
    candidates: str | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the wrapper **inside** `plugin_root`, the way an installed plugin's entry does.

    `CLAUDE_PLUGIN_ROOT` is removed from the environment unless `env_root` names one, and
    `env_root` is deliberately a *different* root: nothing below may change because of it.
    """
    env = dict(os.environ)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if env_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(env_root)
    if candidates is not None:
        env["KEELLINE_PYTHON_CANDIDATES"] = candidates
    return subprocess.run(
        [str(plugin_root / "hooks" / WRAPPER.name), *argv],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def test_no_policy_argument_refuses_with_a_token(tmp_path: Path) -> None:
    # The one failure the wrapper can cause itself. `set -u` alone exits 1 with the shell's own
    # message and no token, which Claude Code reads as a non-blocking error — permission. An
    # entry that loses its first argument must disarm loudly or not at all.
    result = _run(plugin_root=_plugin_root(tmp_path, 0))
    assert result.returncode == 2
    assert "KL_ARGV" in result.stderr


@pytest.mark.parametrize(("policy", "code"), [("closed", 2), ("open", 0)])
def test_no_interpreter_of_the_floor_version_refuses_under_closed_only(
    tmp_path: Path, policy: str, code: int
) -> None:
    # S8 row 1: the wrapper must decide this itself. Every Python-side fallback is unreachable
    # here by construction — there is no interpreter to run it.
    result = _run(
        policy,
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0),
        candidates="/nonexistent/python3",
    )
    assert result.returncode == code
    assert "KL_NO_PY" in result.stderr


def test_an_interpreter_below_the_floor_is_rejected(tmp_path: Path) -> None:
    # S8 row 2, with a real sub-floor interpreter rather than a fake that exits non-zero for
    # every argument. A fake cannot exercise `sys.version_info >= (3, 11)` at all: mutate the
    # predicate to `True` and the fake still refuses, so the row would duplicate the one above
    # and prove nothing. `_old_python` is the tree's own seam for this, and CI pins it through
    # KEELLINE_OLD_PYTHON so the row runs there rather than skipping everywhere.
    old = _old_python()
    if old is None:
        pytest.skip("no interpreter below 3.11 on this machine; set KEELLINE_OLD_PYTHON")
    result = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0),
        candidates=old,
    )
    assert result.returncode == 2
    assert "KL_NO_PY" in result.stderr


def test_an_interpreter_at_the_floor_is_accepted(tmp_path: Path) -> None:
    # The positive row the suite lacks. Without it every interpreter assertion is a refusal,
    # and a probe that rejected *everything* would pass all of them.
    result = _run(
        "closed",
        "hook",
        "PreToolUse",
        plugin_root=_plugin_root(tmp_path, 0),
        candidates=sys.executable,
    )
    assert result.returncode == 0
    assert "KL_NO_PY" not in result.stderr


def test_a_plugin_root_in_the_environment_does_not_choose_the_launcher(tmp_path: Path) -> None:
    # Replaces S8 row 3, whose premise was that the environment names the launcher. It does
    # not: the harness substitutes the plugin root into the *command string* of
    # `hooks/hooks.json`, so the wrapper that runs is always the plugin's own, and the program
    # it hands to Python is derived from that wrapper's path. A variable of the same name
    # arriving from anywhere else — a committed `.claude/settings.json` `env` block is the case
    # `config/machine.py` gates two other variables against — must change nothing, because this
    # choice is made before any Keelline guard runs.
    #
    # The two roots are told apart by their exit codes, not by a message: `theirs` exits 3,
    # which under `closed` policy becomes a KL_RC refusal and exit 2.
    ours = _plugin_root(tmp_path / "ours", 0)
    theirs = _plugin_root(tmp_path / "theirs", 3)
    result = _run("closed", "hook", "PreToolUse", plugin_root=ours, env_root=theirs)
    assert result.returncode == 0
    assert "KL_RC" not in result.stderr


def test_a_missing_launcher_refuses_although_the_environment_names_one(tmp_path: Path) -> None:
    # The refusal the self-derivation still owes: a wrapper with no launcher beside it must
    # say so rather than reach for the one the environment offers. Both arms matter — without
    # the refusal a missing launcher reaches Python as a missing file and exits 2 by CPython
    # accident, with no token to attribute it (D11); without the self-derivation it would run
    # `theirs` and exit 0.
    ours = _plugin_root(tmp_path / "ours", 0, with_launcher=False)
    theirs = _plugin_root(tmp_path / "theirs", 0)
    result = _run("closed", "hook", "PreToolUse", plugin_root=ours, env_root=theirs)
    assert result.returncode == 2
    assert "KL_NO_LAUNCHER" in result.stderr


@pytest.mark.parametrize("rc", [1, 3, 126, 127])
def test_any_other_exit_code_becomes_a_refusal_under_closed(tmp_path: Path, rc: int) -> None:
    # S8 row 5 generalised. 1 is an ImportError, 126 a lost executable bit on the launcher,
    # 127 a missing interpreter the probe somehow accepted; none of them may read as allow.
    result = _run("closed", "hook", "PreToolUse", plugin_root=_plugin_root(tmp_path, rc))
    assert result.returncode == 2
    assert "KL_RC" in result.stderr and str(rc) in result.stderr


@pytest.mark.parametrize("rc", [0, 2])
def test_the_two_platform_codes_pass_through_untouched(tmp_path: Path, rc: int) -> None:
    # The dispatcher owns these two and nothing else may reinterpret them: a 2 it produced is
    # a handler's deny, and the wrapper must not relabel it as its own failure.
    result = _run("closed", "hook", "PreToolUse", plugin_root=_plugin_root(tmp_path, rc))
    assert result.returncode == rc
    assert "keelline:" not in result.stderr


def test_keelline_runs_from_the_project_root(tmp_path: Path) -> None:
    # Every hooks.json entry but the dispatcher's relies on `--root` defaulting to `.`, and the
    # harness does not promise to launch a hook in the project. The wrapper resolves the root —
    # CLAUDE_PROJECT_DIR, else git — and changes into it, so one rule serves every entry.
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    root = _plugin_root(tmp_path, 0, echo_cwd=True)
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project))
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    result = subprocess.run(
        [
            str(root / "hooks" / WRAPPER.name),
            "open",
            "memory",
            "session-context",
            "--bundle",
            "preset-rules",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(elsewhere),
        env=env,
    )
    assert result.stdout.strip() == str(project.resolve())


def test_the_wrapper_is_committed_executable() -> None:
    # S8 row 6 measured that a 0644 wrapper does NOT block: the harness never executes it, so
    # no code of ours runs and no policy applies. The wrapper cannot defend its own mode; this
    # assertion and `doctor`'s wrapper probe (Task 15) are the whole defence.
    assert stat.S_IMODE(WRAPPER.stat().st_mode) & 0o111, "run-hook.sh must ship executable"
