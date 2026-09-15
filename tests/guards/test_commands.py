from __future__ import annotations

import io
import json
import os
import py_compile
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from keelline.cli import build_parser, discover_registrars, run


def invoke(argv: list[str]) -> int:
    return run(argv, parser=build_parser(discover_registrars()))


def feed(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def test_guard_bg_cleanup_refuses_a_leaking_payload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_input": {"command": "sleep 300 & wait", "run_in_background": True}}
    feed(monkeypatch, json.dumps(payload))
    assert invoke(["guard", "bg-cleanup"]) == 2
    assert "refused:" in capsys.readouterr().err


def test_guard_bg_cleanup_accepts_a_bare_tool_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, json.dumps({"command": "make && make test", "run_in_background": True}))
    assert invoke(["guard", "bg-cleanup"]) == 0
    assert "no background leak" in capsys.readouterr().out


def test_guard_bg_cleanup_reports_a_restore_hint_as_a_finding(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    feed(monkeypatch, json.dumps({"command": "cp a a.bak; pytest; cp a.bak a"}))
    assert invoke(["guard", "bg-cleanup", "--json"]) == 1
    assert "trap" in json.loads(capsys.readouterr().out)["hint"]


def test_guard_bg_cleanup_passes_a_payload_for_another_tool_like_the_handler_does(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "x", "run_in_background": True}}
    feed(monkeypatch, json.dumps(payload))
    assert invoke(["guard", "bg-cleanup"]) == 0
    assert "not a Bash call" in capsys.readouterr().out


@pytest.mark.parametrize("stdin", ["not json at all", "[1, 2]", '{"tool_input": "x"}', "{}"])
def test_guard_bg_cleanup_refuses_what_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], stdin: str
) -> None:
    # Fail-closed (§5.2): a guard that cannot read its input must not answer "allowed".
    feed(monkeypatch, stdin)
    assert invoke(["guard", "bg-cleanup"]) == 2
    assert "refused" in capsys.readouterr().err


CONFIG = """
[keelline]
version = "0.1.0"
state = "installed"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "widget"
base_branch = "main"
release_branch = "main"
"""

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(root.parent),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
        },
    ).stdout


def repo(tmp_path: Path, *messages: str) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore: seed")
    git(root, "tag", "base")
    for index, message in enumerate(messages):
        (root / f"f{index}.txt").write_text("x\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", message)
    return root


@needs_git
def test_commit_check_passes_a_clean_range(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(tmp_path, "feat: one", "fix(x): two")
    argv = [
        "commit",
        "check",
        "--range",
        "base..HEAD",
        "--root",
        str(root),
        "--machine",
        str(tmp_path / "m.toml"),
    ]
    assert invoke(argv) == 0
    assert "OK: 2 commit message(s) checked" in capsys.readouterr().out


@needs_git
def test_commit_check_names_the_offence_not_the_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(tmp_path, "fix: dirty\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
    argv = [
        "commit",
        "check",
        "--range",
        "base..HEAD",
        "--root",
        str(root),
        "--machine",
        str(tmp_path / "m.toml"),
        "--json",
    ]
    assert invoke(argv) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["violations"][0]["offences"] == [
        {"line": 3, "label": "attribution trailer naming an AI tool"}
    ]
    assert "noreply@anthropic.com" not in json.dumps(out)


@needs_git
def test_commit_check_refuses_a_range_git_cannot_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(tmp_path)
    argv = [
        "commit",
        "check",
        "--range",
        "nope..HEAD",
        "--root",
        str(root),
        "--machine",
        str(tmp_path / "m.toml"),
    ]
    assert invoke(argv) == 2
    assert "refused" in capsys.readouterr().err


def test_commit_strip_rewrites_the_file_in_place(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(
        "fix: thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n", encoding="utf-8"
    )
    assert invoke(["commit", "strip", str(message)]) == 0
    assert message.read_text(encoding="utf-8") == "fix: thing\n"
    assert "stripped 1" in capsys.readouterr().out


def test_commit_strip_leaves_a_message_that_is_only_attribution(tmp_path: Path) -> None:
    # Emptying it would abort the commit with a confusing "empty message"; CI explains instead.
    message = tmp_path / "COMMIT_EDITMSG"
    original = "Co-Authored-By: Claude <noreply@anthropic.com>\n"
    message.write_text(original, encoding="utf-8")
    assert invoke(["commit", "strip", str(message)]) == 0
    assert message.read_text(encoding="utf-8") == original


def test_commit_strip_keeps_the_files_mode(tmp_path: Path) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fix: t\n\nGenerated with Codex\n", encoding="utf-8")
    message.chmod(0o640)
    assert invoke(["commit", "strip", str(message)]) == 0
    assert (message.stat().st_mode & 0o777) == 0o640


def test_commit_strip_never_writes_through_a_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    real = tmp_path / "real.txt"
    real.write_text("fix: t\n\nGenerated with Codex\n", encoding="utf-8")
    link = tmp_path / "COMMIT_EDITMSG"
    link.symlink_to(real)
    assert invoke(["commit", "strip", str(link)]) == 2
    # `write_atomically` replaces the *link* with a regular file rather than following it, so
    # the target is untouched with or without the guard; what the guard preserves is the link.
    assert link.is_symlink()


def test_commit_strip_refuses_an_option_shaped_path() -> None:
    assert invoke(["commit", "strip", "--", "-weird"]) == 2


def test_commit_strip_keeps_gits_trailing_comment_block_intact(tmp_path: Path) -> None:
    # T5-2: a realistic `prepare-commit-msg` file — subject, blank, an attribution trailer,
    # then git's own comment block (`core.commentChar` default `#`). `offending_lines` judges
    # only the message's *final paragraph* (commit.py's docstring), and in this file that final
    # paragraph is git's comment block, not the trailer — so a strip that does not split the
    # comment block off first would no-op here, on exactly the path the hook exists for.
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(
        "fix: thing\n"
        "\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>\n"
        "\n"
        "# Please enter the commit message for your changes. Lines starting\n"
        "# with '#' will be ignored, and an empty message aborts the commit.\n"
        "#\n"
        "# On branch main\n"
        "# Changes to be committed:\n"
        "#\tnew file:   widget.py\n"
        "#\n",
        encoding="utf-8",
    )
    assert invoke(["commit", "strip", str(message)]) == 0
    result = message.read_text(encoding="utf-8")
    assert result == (
        "fix: thing\n"
        "\n"
        "# Please enter the commit message for your changes. Lines starting\n"
        "# with '#' will be ignored, and an empty message aborts the commit.\n"
        "#\n"
        "# On branch main\n"
        "# Changes to be committed:\n"
        "#\tnew file:   widget.py\n"
        "#\n"
    )
    assert "Co-Authored-By" not in result


@needs_git
def test_test_hygiene_reports_the_two_faults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Exit 1 is "findings", which is what makes this a command and not only a hook notice.
    # Reddened by mutating `run_test_hygiene`'s `exit_code=1 if findings else 0` to `0`;
    # measured. The `roots == 1` assertion has no mutation of its own here — `code_roots` is
    # overridden to the single entry `src`, which exists, so neither the `is_dir()` filter nor
    # the containment call changes this number (both were applied and this test stayed green).
    # It is the wiring assertion: it pins that `--json` reports the walk's own count, and the
    # filter and the containment check are pinned in `tests/guards/test_hygiene.py`.
    root = repo(tmp_path)
    (root / "src").mkdir()
    (root / "src" / "m.py").write_text("x = 1\n", encoding="utf-8")
    (root / "keelline.toml").write_text(
        CONFIG + '\n[ledger]\ncode_roots = ["src"]\n', encoding="utf-8"
    )
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml"), "--json"]
    assert invoke(argv) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["dirty"] >= 1 and out["stale"] == 0 and out["roots"] == 1


@needs_git
def test_test_hygiene_is_clean_on_a_committed_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `repo()` leaves no `[ledger]`, so the roots are the preset's (`src`, `tests`, `scripts`)
    # and none of them exists here: this pins the clean-tree path, not the walk. The walk is
    # pinned in `tests/guards/test_hygiene.py`. Reddened by mutating `run_test_hygiene`'s
    # `exit_code=1 if findings else 0` to `1`; measured.
    root = repo(tmp_path)
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 0
    assert "clean" in capsys.readouterr().out


@needs_git
def test_test_hygiene_refuses_a_tree_git_cannot_report_on(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Not in the ported plan: exit 2 is the third of the three exit codes the CLI row
    # promises, and without this the `Refusal` branch of `run_test_hygiene` is unexercised —
    # deleting it would report an unjudgeable tree as clean and exit 0. Reddened by replacing
    # `raise Refusal(_NO_GIT)` with `found = found._replace(dirty=0)`; measured.
    root = tmp_path / "bare"
    root.mkdir()
    (root / "keelline.toml").write_text(CONFIG, encoding="utf-8")
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 2
    assert "refused:" in capsys.readouterr().err


@needs_git
def test_test_hygiene_names_the_stale_count_in_its_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The summary's stale branch, which nothing else at the CLI level renders: the two tests
    # above report `stale == 0` (and the clean one runs with `roots == 0`), so
    # `f"{found.stale} stale .pyc file(s) under {found.roots} code root(s)"` could be deleted
    # with both still green. The walk itself is pinned in `tests/guards/test_hygiene.py`; this
    # is the string a person reads. Reddened by mutating `run_test_hygiene`'s `if found.stale:`
    # to `if False:`; measured.
    root = repo(tmp_path)
    (root / "src").mkdir()
    module = root / "src" / "m.py"
    module.write_text("x = 1\n", encoding="utf-8")
    # Explicit `cfile` and `TIMESTAMP`, for the reasons `tests/guards/test_hygiene.py`'s
    # `compile_module` gives: `cfile=None` follows `PYTHONPYCACHEPREFIX` out of the fixture,
    # and `SOURCE_DATE_EPOCH` in the environment would make the header hash-based.
    py_compile.compile(
        str(module),
        cfile=str(root / "src" / "__pycache__" / f"m.{sys.implementation.cache_tag}.pyc"),
        doraise=True,
        invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
    )
    future = time.time() + 60
    os.utime(module, (future, future))
    (root / "keelline.toml").write_text(
        CONFIG + '\n[ledger]\ncode_roots = ["src"]\n', encoding="utf-8"
    )
    argv = ["test", "hygiene", "--root", str(root), "--machine", str(tmp_path / "m.toml")]
    assert invoke(argv) == 1
    assert "1 stale .pyc file(s) under 1 code root(s)" in capsys.readouterr().out
