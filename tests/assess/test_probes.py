"""The probes no gate runs: what each finds over files and the git index, and that a probe which
could not look says so instead of reporting nothing.

Every advisory case names the mutation that reddens it in its own comment; the warnings a person
would act on (a committed secret, a query that hid one, the workflow nobody owns) are declared
in `mutations.toml`.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import keelline
from keelline.assess import probes
from keelline.assess.model import WHERE_CAP, Item
from keelline.assess.probes import (
    CODEOWNERS_MAX_BYTES,
    COULD_NOT_LOOK,
    COULD_NOT_LOOK_REMEDY,
    PROBES,
    PROFILE,
    PROFILE_NOT_SHIPPED,
    ProbeContext,
    _owns,
    run_probes,
)
from keelline.config.loader import load, preset_defaults
from keelline.findings import Severity
from keelline.presets import load_preset
from keelline.project.api import CI_WORKFLOW
from tests.assess.smoke import smoke_repo
from tests.gitfixture import git, needs_git, plant_path, run_git

pytestmark = needs_git

# The window a real run reads, from the preset rather than restated.
WINDOW = load_preset("recommended")["assess"]["commit_window"]
# The preset's `[paths] memory`, derived: its literal is on the neutrality denylist for tests.
MEMORY = preset_defaults("widget").paths.memory
OWNED_WORKFLOWS = ".github/workflows/"
# The markers the probe looks for, spelled apart so this file is not one it finds.
TO_DO, FIX_ME, TRIPLE_X = "TO" + "DO", "FIX" + "ME", "X" + "XX"


def _document(extra: str = "") -> str:
    return (
        f'[keelline]\nversion = "{keelline.__version__}"\n{extra}\n\n[project]\nname = "widget"\n'
    )


def _repo(tmp_path: Path, extra: str = "", *, tail: str = "") -> Path:
    """A fresh `git init` holding a minimal `keelline.toml`; `extra` goes into `[keelline]` and
    `tail` after `[project]`. Nothing is committed."""
    root = tmp_path / "widget"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "keelline.toml").write_text(_document(extra) + tail, encoding="utf-8")
    return root


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _commit(root: Path, message: str = "chore: the files") -> None:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


def _all(root: Path, tmp_path: Path) -> list[Item]:
    config = load(root, machine=tmp_path / "m.toml")
    return run_probes(ProbeContext(root, config, WINDOW))


def _items(root: Path, tmp_path: Path, probe: str) -> list[Item]:
    return [item for item in _all(root, tmp_path) if item.probe == probe]


def _shapes(items: list[Item]) -> list[tuple[str, tuple[str, ...]]]:
    return [(item.rule, item.where) for item in items]


def test_every_probe_has_a_distinct_id() -> None:
    # Mutation (advisory): a second `Probe("todo-markers", ...)` in `PROBES` -> reddens.
    ids = [probe.id for probe in PROBES]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 7
    assert {COULD_NOT_LOOK, PROFILE, PROFILE_NOT_SHIPPED}.isdisjoint(ids)


def test_todo_markers_names_each_file_in_the_code_roots_once(tmp_path: Path) -> None:
    # Two markers in one file are one file; a marked file outside the code roots is not read.
    # Mutation (advisory): `"--", *roots` becomes `"--", "."` -> `notes.txt` joins and this
    # reddens.
    root = _repo(tmp_path)
    _write(root, "src/a.txt", f"{TO_DO}: one\n{FIX_ME}: two\n")
    _write(root, "notes.txt", f"{TO_DO}: not code\n")
    _commit(root)
    items = _items(root, tmp_path, "todo-markers")
    assert [(i.rule, i.severity, i.principle, i.where, i.count) for i in items] == [
        ("todo-markers", Severity.ADVICE, 1, ("src/a.txt",), 1)
    ]


def test_the_count_is_whole_past_the_cap(tmp_path: Path) -> None:
    # `where` is capped so an inventory stays a size a reader can hold; the count is the number
    # a person acts on. Mutation (advisory): `len(where)` becomes `len(where[:WHERE_CAP])` in
    # `model.item` -> the count is the cap and this reddens.
    root = _repo(tmp_path)
    for n in range(WHERE_CAP + 50):
        _write(root, f"src/f{n:04}.txt", f"{TRIPLE_X}\n")
    _commit(root)
    (item,) = _items(root, tmp_path, "todo-markers")
    assert len(item.where) == WHERE_CAP
    assert item.count == WHERE_CAP + 50


def test_a_tracked_env_file_is_a_warning_and_an_example_is_not(tmp_path: Path) -> None:
    # Mutation (declared): the predicate's `== ".env"` becomes `== ".nothing"` -> reddens.
    root = _repo(tmp_path)
    _write(root, ".env.example", "KEY=\n")
    _commit(root)
    assert _items(root, tmp_path, "tracked-env") == []
    _write(root, ".env", "KEY=secret\n")
    _commit(root)
    items = _items(root, tmp_path, "tracked-env")
    assert [(i.rule, i.severity, i.where) for i in items] == [
        ("tracked-env", Severity.WARNING, (".env",))
    ]


def test_committed_notes_are_reported_when_the_store_is_not_in_repo(tmp_path: Path) -> None:
    # The preset keeps the store out of git, and history is readable in every clone.
    # Mutation (advisory): `return Looked((store,) if out.strip() else ())` becomes
    # `return Looked()` -> reddens.
    root = _repo(tmp_path)
    _write(root, f"{MEMORY}/note.md", "a note\n")
    _commit(root)
    items = _items(root, tmp_path, "memory-history")
    assert [(i.rule, i.severity, i.principle, i.where) for i in items] == [
        ("memory-history", Severity.WARNING, 8, (MEMORY,))
    ]


def test_committed_notes_in_an_in_repo_store_are_expected(tmp_path: Path) -> None:
    # Mutation (advisory): the `in-repo` early return dropped -> the note is reported, reddens.
    root = _repo(tmp_path, tail='\n[memory]\nmode = "in-repo"\n')
    _write(root, f"{MEMORY}/note.md", "a note\n")
    _commit(root)
    assert _items(root, tmp_path, "memory-history") == []


def test_a_repository_with_no_commit_has_no_history_to_report(tmp_path: Path) -> None:
    # Neither "found" nor "could not look": there is no history yet. `git log --all` on a
    # repository with no commit exits 0 and prints nothing (measured, below), so the probe
    # needs no question about `HEAD` first. Mutation (advisory): the query's `answers` narrowed
    # to exclude 0 -> "could not look" and this reddens.
    root = _repo(tmp_path)
    _write(root, f"{MEMORY}/note.md", "a note\n")
    git(root, "add", "-A")
    assert _items(root, tmp_path, "memory-history") == []


def test_notes_committed_on_another_branch_are_reported_from_an_orphan_one(
    tmp_path: Path,
) -> None:
    # Every clone can read every ref's history, whichever branch is checked out. Asking `HEAD`
    # first made an orphan branch with no commit of its own read as "no history" (found in
    # review). Mutation (advisory): `"--all"` dropped from the query -> `HEAD` has no history,
    # the query exits 128, and this reddens with "could not look".
    root = _repo(tmp_path)
    _write(root, f"{MEMORY}/note.md", "a note\n")
    _commit(root)
    git(root, "checkout", "-q", "--orphan", "fresh")
    items = _items(root, tmp_path, "memory-history")
    assert _shapes(items) == [("memory-history", (MEMORY,))]


def _settings(entry: str) -> str:
    hook = {"type": "command", "command": entry}
    return json.dumps({"hooks": {"PreToolUse": [{"hooks": [hook]}]}})


def test_foreign_hook_entries_are_counted_for_the_selected_harnesses_only(
    tmp_path: Path,
) -> None:
    # Mutation (advisory): `select(...)` replaced by every registered harness -> the Codex file
    # joins `where` and this reddens.
    root = _repo(tmp_path, 'agents = ["claude"]')
    _write(root, ".claude/settings.json", _settings("echo foreign"))
    _write(root, ".codex/hooks.json", _settings("echo foreign"))
    items = _items(root, tmp_path, "foreign-hooks")
    assert [(i.rule, i.severity, i.principle, i.where) for i in items] == [
        ("foreign-hooks", Severity.ADVICE, 5, (".claude/settings.json",))
    ]


def test_keelline_s_own_hook_entries_are_not_foreign(tmp_path: Path) -> None:
    # Mutation (advisory): `marker_id(e["command"]) is None` becomes `True` -> reddens.
    root = _repo(tmp_path, 'agents = ["claude"]')
    _write(root, ".claude/settings.json", _settings("keelline hook x  # keelline:guard"))
    assert _items(root, tmp_path, "foreign-hooks") == []


def test_a_settings_file_keelline_cannot_read_is_named_and_not_fatal(tmp_path: Path) -> None:
    # The engine's own shape check refuses `hooks` as a list; that is "could not look", never
    # "no foreign hook". Mutation (advisory): `EntriesError` dropped from the probe's `except`
    # -> `run_probes` raises and this reddens.
    root = _repo(tmp_path, 'agents = ["claude"]')
    _write(root, ".claude/settings.json", '{"hooks": []}')
    items = _items(root, tmp_path, "foreign-hooks")
    assert _shapes(items) == [(COULD_NOT_LOOK, (".claude/settings.json",))]
    assert [(i.severity, i.principle, i.remedy) for i in items] == [
        (Severity.WARNING, 5, COULD_NOT_LOOK_REMEDY)
    ]


def test_a_settings_file_nested_past_the_parser_s_depth_is_named_and_not_fatal(
    tmp_path: Path,
) -> None:
    # `json` answers deep nesting with `RecursionError`, which no `ValueError` catches.
    # Mutation (advisory): `RecursionError` dropped from the probe's `except` -> reddens.
    root = _repo(tmp_path, 'agents = ["claude"]')
    _write(root, ".claude/settings.json", "[" * 100_000)
    assert _shapes(_items(root, tmp_path, "foreign-hooks")) == [
        (COULD_NOT_LOOK, (".claude/settings.json",))
    ]


def test_a_settings_file_that_is_not_utf_8_is_named_and_not_fatal(tmp_path: Path) -> None:
    # Mutation (advisory): `UnicodeDecodeError` and `ValueError` dropped from the probe's
    # `except` -> `run_probes` raises and this reddens.
    root = _repo(tmp_path, 'agents = ["claude"]')
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.json").write_bytes(b"\xff\xfe{}")
    assert _shapes(_items(root, tmp_path, "foreign-hooks")) == [
        (COULD_NOT_LOOK, (".claude/settings.json",))
    ]


def test_a_git_query_that_does_not_answer_is_not_nothing_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A timeout is `(-1, "")`, and an empty listing read from it would say no `.env` is tracked.
    # Mutation (declared): `return out if code in answers else None` becomes `return out` ->
    # the probe reads `""` as nothing found and this reddens.
    root = _repo(tmp_path)
    _write(root, ".env", "KEY=secret\n")
    _commit(root)
    monkeypatch.setattr(probes, "git_run", lambda *_a, **_k: (-1, ""))
    items = _all(root, tmp_path)
    assert _shapes([i for i in items if i.probe == "tracked-env"]) == [
        (COULD_NOT_LOOK, ("git ls-files",))
    ]
    # Every other git query says so too, and none reads as "nothing found".
    assert {i.probe: i.where for i in items if i.rule == COULD_NOT_LOOK} == {
        "tracked-env": ("git ls-files",),
        "memory-history": ("git log",),
        "commit-types": ("git rev-parse",),
    }


def test_a_path_git_cannot_decode_is_could_not_look_and_not_fatal(tmp_path: Path) -> None:
    # `git ls-files -z` prints a committed name raw; one that is not UTF-8 is `git_run`'s no
    # answer, which is "could not look" and never an exception out of the inventory. The other
    # probes still answer. Mutation: as the case above's, declared there.
    root = _repo(tmp_path)
    _write(root, "README.md", "x\n")
    git(root, "add", "-A")
    plant_path(root, b"caf\xe9.txt")
    git(root, "commit", "-qm", "chore: a name git prints raw")
    items = _all(root, tmp_path)
    assert _shapes([i for i in items if i.probe == "tracked-env"]) == [
        (COULD_NOT_LOOK, ("git ls-files",))
    ]
    assert [i for i in items if i.probe == "commit-types"] == []


def test_workflows_through_a_symlinked_github_are_not_listed(tmp_path: Path) -> None:
    # A workflow listing read through a link lists another directory's files as this one's.
    # Mutation (advisory): `contained(context.root, ".github/workflows")` becomes
    # `context.root / ".github/workflows"` -> the outside files are listed and this reddens.
    root = _repo(tmp_path)
    outside = tmp_path / "outside"
    _write(outside, "workflows/tests.yml", "on: push\n")
    (root / ".github").symlink_to(outside, target_is_directory=True)
    assert _shapes(_items(root, tmp_path, "foreign-workflows")) == [
        (COULD_NOT_LOOK, (".github/workflows",))
    ]


def test_foreign_workflows_are_listed_and_keelline_s_own_is_not(tmp_path: Path) -> None:
    # Mutation (advisory): `if p.name != own` dropped -> `keelline.yml` is listed, reddens.
    root = _repo(tmp_path)
    for name in ("keelline.yml", "tests.yml", "lint.yaml", "notes.txt"):
        _write(root, f".github/workflows/{name}", "on: push\n")
    items = _items(root, tmp_path, "foreign-workflows")
    assert [(i.rule, i.severity, i.principle, i.where) for i in items] == [
        (
            "foreign-workflows",
            Severity.ADVICE,
            None,
            (".github/workflows/lint.yaml", ".github/workflows/tests.yml"),
        )
    ]


@pytest.mark.parametrize(
    ("codeowners", "reported"),
    [
        (None, True),
        ("*.md @owner\n", True),
        ("/.github/ @owner\n", False),
        ("* @owner\n", False),
        ("/.github/workflows/ @owner\n", False),
        ("# /.github/ @owner\n", True),
        ("/.github/ @owner\n/.github/workflows/\n", True),
        ("/.github/workflows/ @owner\n*.md @docs\n", False),
        ("/.github/workflows/* @owner\n", False),
        ("/.github/* @owner\n", True),
        ("/.github/ owner\n", True),
        ("/.github/\n/.github/workflows/ not-an-owner\n", True),
        ("/.github/ @owner someone@example.com @org/team\n", False),
        ("/.github/ @\n", True),
        ("/.github/ foo@\n", True),
        ("/.github/ @@\n", True),
        ("/.github/ @a b@c\n", True),
        ("/.github/ @owner @org/\n", True),
        ("/.github/ @Owner-1 first.last+tag@sub.example.org @my-org/team_a.b\n", False),
        ("/.github/ <someone@example.org>\n", True),
        ('/.github/ "someone"@example.org\n', True),
        ("/.github/ one,two@example.org\n", True),
    ],
    ids=[
        "no-file",
        "another-pattern",
        "github-directory",
        "everything",
        "workflows-directory",
        "a-comment",
        "the-last-match-names-no-one",
        "a-later-line-that-does-not-match",
        "the-workflows-files",
        "direct-children-only",
        "an-owner-github-cannot-read",
        "a-skipped-line-decides-nothing",
        "every-owner-shape",
        "a-bare-at",
        "no-domain",
        "two-ats",
        "an-email-without-a-dot",
        "an-empty-team",
        "every-owner-shape-at-its-edges",
        "an-email-in-angle-brackets",
        "a-quoted-local-part",
        "a-comma-in-the-local-part",
    ],
)
def test_codeowners_is_reported_unless_a_line_owns_the_workflows(
    tmp_path: Path, codeowners: str | None, reported: bool
) -> None:
    # GitHub reads the last matching line, and one with a pattern and no owner leaves the path
    # unowned. Mutation (declared): `owners = words[1:]` becomes `owners = ["x"]` -> the
    # owner-less last line reads as owned and the `the-last-match-names-no-one` case reddens.
    # GitHub skips a line naming an owner that is neither `@user`, `@org/team` nor an email
    # address. Mutation (advisory): that `continue` dropped -> `an-owner-github-cannot-read` is
    # owned by `owner`, and `a-skipped-line-decides-nothing` by `not-an-owner`, where the
    # owner-less line before it decides; both redden. Mutation (declared): the owner's shape
    # read as any word holding `@` -> `a-bare-at`, `no-domain`, `two-ats`,
    # `an-email-without-a-dot` and `an-empty-team` read as owned, and each reddens. Mutation
    # (advisory): the email's local part widened back to `[^@\s]+` and its labels to
    # `[^@\s.]+` -> `an-email-in-angle-brackets`, `a-quoted-local-part` and
    # `a-comma-in-the-local-part` read as owned, and each reddens.
    # `direct-children-only` is GitHub's rule for a last `*` (declared; see the divergence case
    # below).
    root = _repo(tmp_path)
    if codeowners is not None:
        _write(root, ".github/CODEOWNERS", codeowners)
    items = _items(root, tmp_path, "codeowners")
    expected = [("codeowners", Severity.WARNING, 7, (OWNED_WORKFLOWS,))] if reported else []
    assert [(i.rule, i.severity, i.principle, i.where) for i in items] == expected


@pytest.mark.parametrize(
    ("pattern", "reported"),
    [(f"/{CI_WORKFLOW}/", True), ("/.github/**/**/keelline.yml", False)],
    ids=["directory-only", "a-file-below"],
)
def test_a_trailing_slash_owns_a_directory_and_never_a_file_of_that_name(
    tmp_path: Path, pattern: str, reported: bool
) -> None:
    # Mutation (declared): the full-path match no longer skipped for a directory-only pattern ->
    # it owns the file of that name, and the first case reddens.
    root = _repo(tmp_path)
    _write(root, ".github/CODEOWNERS", f"{pattern} @owner\n")
    assert bool(_items(root, tmp_path, "codeowners")) is reported


@pytest.mark.parametrize(
    "pattern",
    ["/.github/workflows/**/keelline.yml", "/.github/**/**/workflows/keelline.yml"],
    ids=["zero-directories", "adjacent"],
)
def test_a_recursive_wildcard_matches_zero_directories_adjacent_ones_included(
    tmp_path: Path, pattern: str
) -> None:
    # `/**/` stands for zero or more directories, so each pattern owns the workflow.
    # Mutation (declared): a `**` that is not last matches one or more components -> `a/**/b`
    # needs a directory between `a` and `b`, and both cases redden.
    root = _repo(tmp_path)
    _write(root, ".github/CODEOWNERS", f"{pattern} @owner\n")
    assert _items(root, tmp_path, "codeowners") == []


# Each one against git's own reading of it, and each outcome is asserted, not just agreement:
# a matcher and an oracle that both answered "no" to everything would agree.
GRAMMAR = [
    "*",
    "*.md",
    "*.yml",
    "/.github/",
    "/.github/workflows/",
    "/.github/workflows/keelline.yml",
    "/.github/workflows/keelline.yml/",
    "/.github/**",
    "/.github/**/",
    "/.github/**/keelline.yml",
    "/.github/**/**/keelline.yml",
    "/.github/workflows/**/keelline.yml",
    "/.github/**/**/workflows/keelline.yml",
    "**/keelline.yml",
    "keelline.yml",
    "workflows/",
    "workflows/keelline.yml",
    ".github/workflows/*.yml",
    "/.github/*/keelline.yml",
    "docs/",
    "/.git*/",
    "/.github/workflow?/",
    "**/workflows/**",
    "/.github/**yml",
    ".github/**yml",
    "/.github/workflows/keelline.yml/**",
    "**",
    "/.github/workflows*/",
    "keelline.yml*",
    "/.github/*/*/",
    "/.github/*/",
    "*/",
    "/*/",
    "/***/keelline.yml",
    "***/keelline.yml",
    "/.github/****/",
    "/.github/***",
    "/.github/***yml",
]


def _git_ignores(tmp_path: Path, pattern: str) -> bool:
    scratch = tmp_path / "scratch"
    if not scratch.exists():
        scratch.mkdir()
        git(scratch, "init", "-q")
        _write(scratch, CI_WORKFLOW, "on: push\n")
    (scratch / ".gitignore").write_text(pattern + "\n", encoding="utf-8")
    done = run_git(scratch, "check-ignore", "--no-index", "-q", CI_WORKFLOW)
    assert done.returncode in (0, 1), done.stderr
    return done.returncode == 0


def test_the_matcher_agrees_with_git_on_its_grammar(tmp_path: Path) -> None:
    # An independent oracle for the patterns GitHub shares with gitignore. Mutations (declared):
    # the directory-only rule, `**` as zero or more components, and `**` special only as a
    # whole component (`**yml` is `*yml`) each make some pattern disagree. A whole component of
    # three or more `*` is git's `**` (found by fuzzing against git; GitHub documents nothing
    # here, so git decides). Mutation (advisory): that reading dropped -> `/***/keelline.yml`
    # and its siblings disagree, and this reddens.
    ours = {p: _owns(p, CI_WORKFLOW) for p in GRAMMAR}
    theirs = {p: _git_ignores(tmp_path, p) for p in GRAMMAR}
    assert ours == theirs
    assert {p for p, owned in theirs.items() if not owned} == {
        "*.md",
        "/.github/workflows/keelline.yml/",
        "workflows/keelline.yml",
        "docs/",
        "/.github/**yml",
        ".github/**yml",
        "/.github/workflows/keelline.yml/**",
        "/.github/*/*/",
        "/.github/***yml",
    }


def test_a_last_star_owns_direct_children_only_where_github_and_git_differ(
    tmp_path: Path,
) -> None:
    # The one place this matcher is GitHub's and not git's. GitHub documents that `docs/*` owns
    # the files directly in `docs` and not a file nested below one of its directories; git
    # matches the directory itself, and so everything below it. Mutation (declared): the
    # last-`*` rule dropped -> `/.github/*` owns the workflow as git reads it, and this reddens.
    assert _git_ignores(tmp_path, "/.github/*")
    assert not _owns("/.github/*", CI_WORKFLOW)
    assert _owns("/.github/workflows/*", CI_WORKFLOW)
    assert _owns("*", CI_WORKFLOW)


@pytest.mark.parametrize("pattern", ["/.github/*/", "*/", "/*/"])
def test_a_directory_only_last_star_owns_what_is_below_each_directory_it_matches(
    pattern: str,
) -> None:
    # GitHub's direct-children rule is about the files a last `*` names; a trailing `/` names
    # directories instead, and a directory it matches owns everything below it, as git reads
    # it (these three are in the git-agreement list too). Found in review: the rule ran before
    # the directory check and left `docs/*/` owning nothing at all. Mutation (advisory):
    # `and not directory` dropped from that rule -> each case reddens.
    assert _owns(pattern, CI_WORKFLOW)


# Each runs in a child with a deadline, so a matcher that backtracks fails this case instead of
# hanging the suite. Every pattern is the repository's to write: a run of `*`, a run of `**`
# components long enough to exhaust a recursion, and a component of alternating stars.
BOUNDED = (
    "from keelline.assess.probes import _owns\n"
    "from keelline.project.api import CI_WORKFLOW\n"
    "for pattern in ('*' * 100_000 + 'z', '**/' * 100_000 + 'z', '*e' * 50_000 + 'z',\n"
    "                '/'.join(['*'] * 100_000)):\n"
    "    print(_owns(pattern, CI_WORKFLOW))\n"
)


DEADLINE_SECONDS = 20


def test_a_pattern_of_many_wildcards_is_answered_promptly() -> None:
    # Found in review: a regex with one `[^/]*` per `*` took 2.4 s at twenty asterisks and grew
    # sevenfold per four more, so one CODEOWNERS line could hold `keelline assess` for good.
    # The matcher has no regex now: `_glob` keeps one resumption point and moves it on at every
    # retry, and the component table visits each cell once. Mutation (declared): `resume += 1`
    # becomes `resume += 0` -> `_glob` retries the same position for ever, the child runs past
    # its deadline, and this reddens with the deadline's message. Mutation (advisory): adjacent
    # `**` no longer collapsed, or the component-count bound dropped -> survives: either makes
    # the table larger, not the walk any less linear, which is why neither is this case's guard.
    try:
        done = subprocess.run(
            [sys.executable, "-c", BOUNDED],
            capture_output=True,
            text=True,
            check=False,
            timeout=DEADLINE_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"the matcher ran past {DEADLINE_SECONDS} s on a pattern the repository wrote")
    assert (done.returncode, done.stdout.split()) == (0, ["False"] * 4), done.stderr


def test_a_codeowners_file_github_does_not_load_owns_nothing(tmp_path: Path) -> None:
    # GitHub does not load a code-owners file of 3 MB or more. Mutation (advisory): the size
    # check dropped -> the `*` line is read and owns the workflow, and this reddens.
    root = _repo(tmp_path)
    line = "* @owner\n"
    _write(root, ".github/CODEOWNERS", line + "#" * (CODEOWNERS_MAX_BYTES - len(line)))
    assert _shapes(_items(root, tmp_path, "codeowners")) == [("codeowners", (OWNED_WORKFLOWS,))]
    _write(root, ".github/CODEOWNERS", line + "#" * (CODEOWNERS_MAX_BYTES - len(line) - 1))
    assert _items(root, tmp_path, "codeowners") == []


def test_a_codeowners_file_under_another_case_owns_nothing(tmp_path: Path) -> None:
    # GitHub reads only the exact name. Mutation (advisory): `_exact_file(path)` becomes
    # `path.is_file()` -> reddens only where the filesystem folds case (the macOS and Windows
    # defaults); on a case-sensitive CI runner no single-line mutation reddens this, since the
    # lower-case file is then simply absent under the name asked for.
    root = _repo(tmp_path)
    _write(root, ".github/codeowners", "/.github/ @owner\n")
    assert _shapes(_items(root, tmp_path, "codeowners")) == [("codeowners", (OWNED_WORKFLOWS,))]


def test_the_first_codeowners_file_that_exists_is_the_only_one_read(tmp_path: Path) -> None:
    # GitHub reads `.github/CODEOWNERS` before the root's, and reads one file. Mutation
    # (advisory): the loop walks `reversed(_CODEOWNERS)` -> the root file's owner is read and
    # this reddens.
    root = _repo(tmp_path)
    _write(root, ".github/CODEOWNERS", "*.md @docs\n")
    _write(root, "CODEOWNERS", "* @owner\n")
    assert _shapes(_items(root, tmp_path, "codeowners")) == [("codeowners", (OWNED_WORKFLOWS,))]


def test_a_codeowners_file_through_a_symlink_is_could_not_look(tmp_path: Path) -> None:
    # Mutation (advisory): `PathEscape` dropped from the codeowners `except` -> reddens on the
    # exception.
    root = _repo(tmp_path)
    _write(tmp_path, "elsewhere", "* @owner\n")
    (root / "CODEOWNERS").symlink_to(tmp_path / "elsewhere")
    assert _shapes(_items(root, tmp_path, "codeowners")) == [(COULD_NOT_LOOK, ("CODEOWNERS",))]


def test_codeowners_is_not_judged_when_keelline_renders_no_workflow(tmp_path: Path) -> None:
    # Mutation (advisory): the `ci.mode == "none"` early return dropped -> reddens.
    root = _repo(tmp_path, tail='\n[ci]\nmode = "none"\n')
    assert _items(root, tmp_path, "codeowners") == []


def test_commit_subjects_outside_the_vocabulary_are_counted_by_sha(tmp_path: Path) -> None:
    # Each subject carries a byte `str.splitlines` breaks on and git keeps; only NUL delimits.
    # Mutation (advisory): `fields = out.split("\0")` becomes
    # `fields = "\0".join(out.splitlines()).split("\0")` -> the pairs shift and this reddens.
    root = _repo(tmp_path)
    for n, subject in enumerate(
        ("feat: one\u2028line", "fix(x): two\x1cparts", "wip", "Update README.md")
    ):
        _write(root, f"f{n}.txt", f"{n}\n")
        _commit(root, subject)
    shas = git(root, "log", "--format=%H", "-2").split()
    items = _items(root, tmp_path, "commit-types")
    assert [(i.rule, i.severity, i.principle) for i in items] == [
        ("commit-types", Severity.ADVICE, None)
    ]
    assert sorted(items[0].where) == sorted(shas)


def test_a_repository_with_no_commit_has_no_subject_to_count(tmp_path: Path) -> None:
    # Mutation (advisory): the no-commit return dropped from `_commit_types` -> `git log` on an
    # unborn branch exits 128, which is "could not look", and this reddens.
    root = _repo(tmp_path)
    assert _items(root, tmp_path, "commit-types") == []


def test_a_profile_s_failed_check_is_one_item_at_its_own_level(tmp_path: Path) -> None:
    # Mutation (advisory): the explicit count `1` dropped -> `type-checker` counts its eleven
    # locators' seven distinct `at` names and this reddens.
    root = _repo(tmp_path, 'profile = "python"')
    _write(root, "pyproject.toml", '[project]\nname = "widget"\n')
    items = {i.rule: i for i in _items(root, tmp_path, PROFILE)}
    assert {"requires-python", "type-checker"} <= set(items)
    assert items["requires-python"].severity is Severity.WARNING
    assert items["type-checker"].severity is Severity.ADVICE
    assert items["type-checker"].count == 1
    assert "pyproject.toml" in items["type-checker"].where


def test_a_profile_check_git_could_not_answer_is_could_not_look_not_untracked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A `tracked` check git gave no answer for has not passed and has not failed. Mutation
    # (advisory): `if outcome.located:` becomes `if True:` -> the unanswered outcome is an
    # item under its check's id, read as an untracked lockfile, and this reddens.
    # `keelline.profiles.evaluate` is the function on the package; the module is asked for.
    profile_evaluate = importlib.import_module("keelline.profiles.evaluate")
    root = _repo(tmp_path, 'profile = "python"')
    _write(root, "pyproject.toml", '[project]\nname = "widget"\n')
    _write(root, "uv.lock", "version = 1\n")
    monkeypatch.setattr(profile_evaluate, "git_run", lambda *_a, **_k: (-1, ""))
    items = _items(root, tmp_path, PROFILE)
    assert "lockfile-untracked" not in {i.rule for i in items}
    assert [(i.severity, i.where, i.remedy) for i in items if i.rule == COULD_NOT_LOOK] == [
        (Severity.WARNING, ("uv.lock",), COULD_NOT_LOOK_REMEDY)
    ]


def test_a_profile_this_keelline_does_not_ship_is_one_warning_and_the_rest_still_runs(
    tmp_path: Path,
) -> None:
    # Mutation (advisory): the `shipped()` check dropped -> `ProfileError` ends `run_probes`.
    root = _repo(tmp_path, 'profile = "no-such-profile"')
    items = _all(root, tmp_path)
    profile = [i for i in items if i.probe == PROFILE]
    assert [(i.rule, i.severity, i.where) for i in profile] == [
        (PROFILE_NOT_SHIPPED, Severity.WARNING, ("[keelline] profile",))
    ]
    assert "python" in profile[0].remedy
    assert [i.probe for i in items if i.probe != PROFILE] == ["codeowners"]


def test_no_profile_configured_reports_no_profile_item(tmp_path: Path) -> None:
    # The preset's `profile = ""` is no profile. Mutation (advisory): the empty-name return
    # dropped -> `""` is not shipped, a `profile-not-shipped` item appears and this reddens.
    root = _repo(tmp_path)
    assert load(root, machine=tmp_path / "m.toml").keelline.profile == ""
    assert _items(root, tmp_path, PROFILE) == []


def test_the_smoke_copy_warns_only_that_nobody_owns_the_workflow(tmp_path: Path) -> None:
    # The fixture every gate passes on has no CODEOWNERS file, and nothing else to warn about.
    root = smoke_repo(tmp_path)
    config = load(root, machine=tmp_path / "m.toml")
    items = run_probes(ProbeContext(root, config, WINDOW))
    assert [(i.probe, i.rule) for i in items if i.severity is Severity.WARNING] == [
        ("codeowners", "codeowners")
    ]


def test_a_probe_s_attributes_are_the_item_s(tmp_path: Path) -> None:
    # `run_probes` builds each item from its `Probe`, so the attribute a test reads off `PROBES`
    # is the one an item carries. Mutation (advisory): `principle=probe.principle` becomes
    # `principle=None` in `run_probes` -> reddens.
    root = _repo(tmp_path)
    _write(root, ".env", "KEY=secret\n")
    _commit(root, "wip")
    by_id = {probe.id: probe for probe in PROBES}
    items = [i for i in _all(root, tmp_path) if i.probe in by_id]
    assert {i.probe for i in items} >= {"tracked-env", "commit-types", "codeowners"}
    for i in items:
        probe = by_id[i.probe]
        assert (i.rule, i.principle, i.severity, i.remedy) == (
            probe.id,
            probe.principle,
            probe.severity,
            probe.remedy,
        )


def test_the_git_bound_is_the_query_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Every probe query runs under `QUERY_TIMEOUT_SECONDS`, not `git_run`'s five-second default
    # meant for a `rev-parse`. Mutation (advisory): `timeout=QUERY_TIMEOUT_SECONDS` dropped from
    # `_git` -> the default arrives and this reddens.
    seen: list[float] = []

    def recording(
        root: Path, *args: str, timeout: float = 5, stdin: str | None = None
    ) -> tuple[int, str]:
        seen.append(timeout)
        return (-1, "")

    root = _repo(tmp_path)
    monkeypatch.setattr(probes, "git_run", recording)
    _all(root, tmp_path)
    assert seen
    assert set(seen) == {probes.QUERY_TIMEOUT_SECONDS}


def test_the_probes_git_bound_is_the_ledger_s() -> None:
    # The value mirrors the ledger's own bound on a local query, which is private to that area.
    # Mutation (advisory): either constant changed alone -> reddens.
    from keelline.ledger.git import QUERY_TIMEOUT_SECONDS as LEDGER_BOUND

    assert probes.QUERY_TIMEOUT_SECONDS == LEDGER_BOUND


def test_git_log_all_on_a_repository_with_no_commit_answers_zero(tmp_path: Path) -> None:
    # The measurement the no-commit case above rests on: were this to exit outside `(0,)`, the
    # early return in `_memory_history` would be what kept that case from "could not look".
    root = _repo(tmp_path)
    done = run_git(root, "log", "--all", "--format=%H", "-1", "--", MEMORY)
    assert (done.returncode, done.stdout) == (0, "")
