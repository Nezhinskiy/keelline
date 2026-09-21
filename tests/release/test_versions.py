from __future__ import annotations

import json
from pathlib import Path

import pytest

from keelline.cli import build_parser, run
from keelline.release.commands import register
from keelline.release.versions import MalformedSource, check, collect, pending_fragments

ROOT = Path(__file__).resolve().parents[2]

# The fragment predicate reads the types towncrier itself is configured with, so a fixture
# repository has to declare them exactly as the real one does.
PYPROJECT = """[project]
name = "keelline"
version = "{v}"

[[tool.towncrier.type]]
directory = "feature"

[[tool.towncrier.type]]
directory = "fix"

[[tool.towncrier.type]]
directory = "change"
"""
INIT = '__version__ = "{v}"\n'
LOCK = '[[package]]\nname = "keelline"\nversion = "{v}"\nsource = {{ editable = "." }}\n'
MARKETPLACE = {"name": "keelline-marketplace", "plugins": [{"name": "keelline", "source": "./"}]}


def repo(
    tmp_path: Path,
    *,
    pyproject: str,
    init: str,
    claude: str,
    codex: str,
    changelog: str,
    lock: str | None = None,
    fragments: int = 0,
    marketplace: dict[str, object] | None = None,
) -> Path:
    (tmp_path / "src" / "keelline").mkdir(parents=True)
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".codex-plugin").mkdir()
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.format(v=pyproject))
    (tmp_path / "uv.lock").write_text(LOCK.format(v=pyproject if lock is None else lock))
    (tmp_path / "src" / "keelline" / "__init__.py").write_text(INIT.format(v=init))
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "keelline", "version": claude})
    )
    (tmp_path / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(marketplace or MARKETPLACE)
    )
    (tmp_path / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "keelline", "version": codex})
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n<!-- towncrier release notes start -->\n\n"
        f"## {changelog} (2026-09-05)\n"
    )
    for index in range(fragments):
        (tmp_path / "changelog.d" / f"{index}.feature.md").write_text("x\n")
    return tmp_path


def test_all_equal_is_clean(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.1.0", claude="0.1.0", codex="0.1.0", changelog="0.1.0"
    )
    assert check(root) == []


def test_each_mismatch_is_named(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.1.0", claude="0.1.1", codex="0.1.0", changelog="0.1.0"
    )
    problems = check(root)
    assert len(problems) == 1
    assert ".claude-plugin/plugin.json" in problems[0]
    assert "0.1.1" in problems[0]


def test_pending_fragments_allow_the_changelog_to_lag(tmp_path: Path) -> None:
    root = repo(
        tmp_path,
        pyproject="0.2.0",
        init="0.2.0",
        claude="0.2.0",
        codex="0.2.0",
        changelog="0.1.0",
        fragments=1,
    )
    assert check(root) == []


def test_without_fragments_the_changelog_must_match(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="0.2.0", init="0.2.0", claude="0.2.0", codex="0.2.0", changelog="0.1.0"
    )
    assert any("CHANGELOG.md" in problem for problem in check(root))


def test_a_versioned_marketplace_entry_is_refused(tmp_path: Path) -> None:
    versioned: dict[str, object] = {
        "name": "m",
        "plugins": [{"name": "keelline", "source": "./", "version": "0.1.0"}],
    }
    root = repo(
        tmp_path,
        pyproject="0.1.0",
        init="0.1.0",
        claude="0.1.0",
        codex="0.1.0",
        changelog="0.1.0",
        marketplace=versioned,
    )
    assert any("marketplace" in problem for problem in check(root))


def test_collect_reads_every_source_value(tmp_path: Path) -> None:
    root = repo(
        tmp_path,
        pyproject="1.0.0",
        init="1.0.1",
        claude="1.0.2",
        codex="1.0.3",
        changelog="1.0.4",
        lock="1.0.5",
    )
    assert collect(root) == {
        "pyproject.toml": "1.0.0",
        "uv.lock": "1.0.5",
        "src/keelline/__init__.py": "1.0.1",
        ".claude-plugin/plugin.json": "1.0.2",
        ".codex-plugin/plugin.json": "1.0.3",
        "CHANGELOG.md": "1.0.4",
    }


def test_a_missing_version_key_reads_as_none(tmp_path: Path) -> None:
    root = repo(
        tmp_path, pyproject="1.0.0", init="1.0.0", claude="1.0.0", codex="1.0.0", changelog="1.0.0"
    )
    (root / ".codex-plugin" / "plugin.json").write_text(json.dumps({"name": "keelline"}))
    assert collect(root)[".codex-plugin/plugin.json"] is None


def test_the_cli_command_exits_one_on_version_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # CI runs the success path on every build, so exit 1 — C6's only user-facing surface —
    # is reached by nothing else.
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.2.0", claude="0.1.0", codex="0.1.0", changelog="0.1.0"
    )
    assert run(["release", "check", "--root", str(root)], parser=build_parser([register])) == 1
    # stdout, and that is the change rather than an accident: this area used to report a
    # finding by raising `Failure`, which the frame prints to stderr under a `keelline: failed:`
    # prefix and which drops `Result.data`. Every other area returns its findings.
    assert "version drift" in capsys.readouterr().out


def test_the_json_object_has_the_same_shape_whether_or_not_there_is_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The whole of why this area stopped raising. A `Failure` becomes
    # `{"error": "failed", "summary": "failed: ..."}` and `Result.data` never reaches the
    # output — so a consumer that read `versions` on a clean run had nothing to read on the run
    # it cared about, and the machine-readable shape flipped on exactly the condition being
    # tested for. Asserted as the key sets being equal AND as the drifted run carrying the
    # data: "both objects are empty" would satisfy the first on its own.
    #
    # Mutation (declared): the drift arm returns `{}` for its data, which is what raising
    # produced -> the key sets differ and this reddens naming them.
    clean = repo(
        tmp_path / "a",
        pyproject="0.1.0",
        init="0.1.0",
        claude="0.1.0",
        codex="0.1.0",
        changelog="0.1.0",
    )
    drifted = repo(
        tmp_path / "b",
        pyproject="0.1.0",
        init="0.2.0",
        claude="0.1.0",
        codex="0.1.0",
        changelog="0.1.0",
    )
    parser = build_parser([register])
    assert run(["release", "check", "--root", str(clean), "--json"], parser=parser) == 0
    on_success = json.loads(capsys.readouterr().out)
    assert run(["release", "check", "--root", str(drifted), "--json"], parser=parser) == 1
    on_drift = json.loads(capsys.readouterr().out)

    assert set(on_success) == set(on_drift) == {"summary", "problems", "versions"}
    assert on_success["problems"] == []
    assert on_drift["problems"] == [
        "src/keelline/__init__.py says '0.2.0'; pyproject.toml says '0.1.0'"
    ]
    assert on_drift["versions"]["src/keelline/__init__.py"] == "0.2.0"


def test_the_cli_command_reports_the_agreed_version_on_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repo(
        tmp_path, pyproject="0.1.0", init="0.1.0", claude="0.1.0", codex="0.1.0", changelog="0.1.0"
    )
    argv = ["release", "check", "--root", str(root), "--json"]
    assert run(argv, parser=build_parser([register])) == 0
    assert json.loads(capsys.readouterr().out)["versions"]["pyproject.toml"] == "0.1.0"


def _repo(
    tmp_path: Path,
    *,
    pyproject: str = "0.1.0",
    init: str = "0.1.0",
    claude: str = "0.1.0",
    codex: str = "0.1.0",
    changelog: str = "0.1.0",
    lock: str | None = None,
) -> Path:
    """`repo` with every version agreeing unless a test disagrees with one on purpose."""
    return repo(
        tmp_path,
        pyproject=pyproject,
        init=init,
        claude=claude,
        codex=codex,
        changelog=changelog,
        lock=lock,
    )


@pytest.mark.parametrize(
    ("entry", "pending"),
    [
        ("x.feature.md", True),
        ("0.fix.md", True),
        ("a.b.change.md", True),
        (".gitkeep", False),
        (".DS_Store", False),
        ("notes.md", False),
        ("x.bogus.md", False),
        ("feature.md", False),
        ("x.feature.rst", False),
    ],
)
def test_only_a_towncrier_fragment_lets_the_changelog_lag(
    tmp_path: Path, entry: str, pending: bool
) -> None:
    # A stray .DS_Store — which Finder writes just by opening changelog.d — used to count as a
    # pending fragment and turn a genuine drift from exit 1 into exit 0.
    root = _repo(tmp_path, pyproject="0.2.0", init="0.2.0", claude="0.2.0", codex="0.2.0")
    (root / "changelog.d" / entry).write_text("x\n")
    assert pending_fragments(root) is pending
    assert (check(root) == []) is pending


def test_a_stray_file_beside_a_real_fragment_does_not_hide_it(tmp_path: Path) -> None:
    root = _repo(tmp_path, pyproject="0.2.0", init="0.2.0", claude="0.2.0", codex="0.2.0")
    (root / "changelog.d" / ".DS_Store").write_text("x\n")
    (root / "changelog.d" / "foundation.feature.md").write_text("x\n")
    assert pending_fragments(root) is True


def test_the_fragment_types_come_from_the_configuration_not_from_code(tmp_path: Path) -> None:
    # Hardcoding "feature", "fix", "change" here would drift from the [[tool.towncrier.type]]
    # blocks towncrier itself reads.
    root = _repo(tmp_path, pyproject="0.2.0", init="0.2.0", claude="0.2.0", codex="0.2.0")
    (root / "changelog.d" / "x.removal.md").write_text("x\n")
    assert pending_fragments(root) is False
    pyproject = root / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text() + '\n[[tool.towncrier.type]]\ndirectory = "removal"\n'
    )
    assert pending_fragments(root) is True


def test_a_disagreeing_lockfile_is_reported_by_name(tmp_path: Path) -> None:
    # `uv sync --locked` reds the install step on a stale lockfile with a dependency-shaped
    # message, ahead of the gate built to catch exactly this.
    root = _repo(tmp_path, lock="0.0.9")
    problems = check(root)
    assert len(problems) == 1
    assert "uv.lock says '0.0.9'" in problems[0]


def test_a_missing_lockfile_reads_as_none_and_is_reported_as_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "uv.lock").unlink()
    assert collect(root)["uv.lock"] is None
    assert any("uv.lock says None" in problem for problem in check(root))


def test_a_lockfile_that_names_no_keelline_package_reads_as_none(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "uv.lock").write_text('[[package]]\nname = "pytest"\nversion = "8.0.0"\n')
    assert collect(root)["uv.lock"] is None


def test_the_four_root_conditions_get_four_different_messages(tmp_path: Path) -> None:
    # One shared message told a user who typoed --root, or ran the command in their own
    # project (--root defaults to "."), that their pyproject.toml lacked a version key. The
    # file case then inherited the missing-path message, so `--root ./pyproject.toml` was told
    # a file it had just been handed does not exist — the gate asserting something untrue
    # about the user's tree, which is the very thing these messages exist to stop.
    missing = tmp_path / "nope"
    not_a_directory = tmp_path / "pyproject.toml"
    not_a_directory.write_text('[project]\nname = "keelline"\nversion = "0.1.0"\n')
    empty = tmp_path / "empty"
    empty.mkdir()
    no_version = tmp_path / "no-version"
    no_version.mkdir()
    (no_version / "pyproject.toml").write_text('[project]\nname = "keelline"\n')

    absent = check(missing)
    a_file = check(not_a_directory)
    unrelated = check(empty)
    versionless = check(no_version)
    assert absent == [f"{missing} does not exist; --root must name a repository root"]
    assert a_file == [f"{not_a_directory} is not a directory; --root must name a repository root"]
    assert unrelated == [f"{empty} has no pyproject.toml; --root must name a repository root"]
    assert versionless == ["pyproject.toml has no [project].version"]
    assert len({tuple(absent), tuple(a_file), tuple(unrelated), tuple(versionless)}) == 4


@pytest.mark.parametrize(
    ("name", "body", "kind"),
    [
        ("pyproject.toml", "not = = toml", "TOML"),
        ("uv.lock", "not = = toml", "TOML"),
        (".claude-plugin/plugin.json", "{not json", "JSON"),
        (".codex-plugin/plugin.json", "{not json", "JSON"),
    ],
)
def test_a_malformed_source_is_reported_with_its_filename(
    tmp_path: Path, name: str, body: str, kind: str
) -> None:
    # `_read` knows the filename and used to let the decoder's own error escape without it.
    root = _repo(tmp_path)
    (root / name).write_text(body)
    with pytest.raises(MalformedSource) as raised:
        check(root)
    assert name in str(raised.value)
    assert kind in str(raised.value)


@pytest.mark.parametrize(
    "body",
    ['package = "not-a-list"\n', "package = [1, 2]\n"],
    ids=["not-a-list", "entries-not-tables"],
)
def test_a_wrongly_shaped_lockfile_is_reported_by_name(tmp_path: Path, body: str) -> None:
    # Valid TOML of the wrong shape decodes cleanly, so `_read`'s two decoder catches never see
    # it: iterating a string yields characters and `entry.get` raised AttributeError straight
    # past them, reaching the caller as an unlabelled internal error naming no file.
    root = _repo(tmp_path)
    (root / "uv.lock").write_text(body)
    with pytest.raises(MalformedSource) as raised:
        check(root)
    assert "uv.lock" in str(raised.value)


def test_the_cli_command_exits_one_on_a_malformed_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # `MalformedSource` derives from `Failure` on purpose: a source the gate cannot parse is a
    # finding, not a refusal. Nothing observed that through `run` — the unit tests catch the
    # class, which is base-class agnostic — so reverting it to `Refusal`, and exit 2 with it,
    # left every test green.
    root = _repo(tmp_path)
    (root / "uv.lock").write_text("not = = toml")
    assert run(["release", "check", "--root", str(root)], parser=build_parser([register])) == 1
    assert "uv.lock is not valid TOML" in capsys.readouterr().err


def _at(tmp_path: Path, version: str) -> Path:
    """The module's `_repo` with every source at one version.

    The plan named a `_repository(tmp_path, version=…)` fixture this module has never had;
    `_repo` is the one that exists and it takes a keyword per source, so the two tests below
    say the version once through here rather than five times each.
    """
    return _repo(
        tmp_path,
        pyproject=version,
        init=version,
        claude=version,
        codex=version,
        changelog=version,
    )


def test_a_tag_that_names_another_version_is_drift(tmp_path: Path) -> None:
    # The release workflow used to compare the tag to the package in shell; the gate that
    # exists to say "one version everywhere" now takes the tag as a seventh source. Both
    # tag shapes are accepted — `vX.Y.Z` (the workflow's trigger) and the platform's
    # `keelline--vX.Y.Z` — because either may be the one the run was created from.
    # Mutation (declared): accept any tag -> the first assertion reddens.
    root = _at(tmp_path, "1.2.3")
    assert check(root, tag="v1.2.4") == [
        "tag v1.2.4 is neither v1.2.3 nor keelline--v1.2.3; pyproject.toml says '1.2.3'"
    ]
    assert check(root, tag="v1.2.3") == []
    assert check(root, tag="keelline--v1.2.3") == []


def test_the_drift_message_says_what_was_checked_rather_than_inventing_a_version(
    tmp_path: Path,
) -> None:
    # The message used to be derived with `tag.split("v", 1)[-1]` — a split on the first `v`
    # anywhere in the string, not a parse — so it named a version the tag does not carry.
    # Measured on this repository before the fix:
    #
    #   --tag 0.1.0          -> tag 0.1.0 names 0.1.0; pyproject.toml says '0.1.0'
    #   --tag keelline-v0.1.0 -> tag keelline-v0.1.0 names 0.1.0; …says '0.1.0'
    #   --tag dev-v0.1.0     -> tag dev-v0.1.0 names -v0.1.0; …says '0.1.0'
    #
    # The first asserts that two identical strings disagree, which is the failure the comment
    # above `check` was written to end. Both of the first two are the slips `RELEASING.md`
    # invites: a human types this flag by hand right after a tool prints `keelline--vX.Y.Z`.
    # The tags the older case exercised (`v1.2.4`, `v9.9.9`) all begin with `v` and carry no
    # earlier one, so the split happened to be right and the tests passed for that reason.
    #
    # Mutation (declared): the derived `named` comes back -> all three assertions redden.
    root = _at(tmp_path, "1.2.3")
    # A bare version, which is the tag `git tag 1.2.3` makes and the one that read as agreeing
    # with itself.
    assert check(root, tag="1.2.3") == [
        "tag 1.2.3 is neither v1.2.3 nor keelline--v1.2.3; pyproject.toml says '1.2.3'"
    ]
    # One hyphen short of the platform's own tag.
    assert check(root, tag="keelline-v1.2.3") == [
        "tag keelline-v1.2.3 is neither v1.2.3 nor keelline--v1.2.3; pyproject.toml says '1.2.3'"
    ]
    # And a prefix carrying an earlier `v`, where the split produced `-v1.2.3` — a string that
    # is not a version at all.
    assert check(root, tag="dev-v1.2.3") == [
        "tag dev-v1.2.3 is neither v1.2.3 nor keelline--v1.2.3; pyproject.toml says '1.2.3'"
    ]


def test_a_tag_with_pending_fragments_is_refused(tmp_path: Path) -> None:
    # Without `--tag`, pending fragments let CHANGELOG.md lag, because a lane's fragment is
    # written before the release assembles it. AT a tag there is nothing left to assemble:
    # a fragment still pending means the changelog the users read is not the one the tag
    # claims. Mutation (declared): skip the fragment check under `tag` -> reddens.
    root = _at(tmp_path, "1.2.3")
    (root / "changelog.d" / "late.feature.md").write_text("late\n", encoding="utf-8")
    assert check(root) == []
    problems = check(root, tag="v1.2.3")
    assert problems == [
        "changelog.d still holds 1 fragment(s); run "
        "`keelline release notes --version 1.2.3` before tagging"
    ]


def test_the_cli_passes_the_tag_through_to_the_gate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # That the flag exists is held by the README row walk, which parses every row against the
    # real parser; that its value reaches `check` is held here and nowhere else. Mutation:
    # `check(root, tag=args.tag)` -> `check(root)` -> exit 0 and this reddens.
    root = _at(tmp_path, "1.2.3")
    argv = ["release", "check", "--root", str(root), "--tag", "v9.9.9"]
    assert run(argv, parser=build_parser([register])) == 1
    assert "tag v9.9.9 is neither v1.2.3 nor" in capsys.readouterr().out


def test_the_cli_refuses_notes_under_a_version_that_is_not_the_projects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Exit 2, the refusal code, and no towncrier anywhere: the comparison is above the runner,
    # so this walks the registered command end to end without shelling out — which the global
    # constraints forbid a test to do. The write path stays a unit test over the stub.
    root = _at(tmp_path, "1.2.3")
    argv = ["release", "notes", "--version", "1.3.0", "--root", str(root)]
    assert run(argv, parser=build_parser([register])) == 2
    assert "set the version everywhere first" in capsys.readouterr().err


def test_a_project_with_its_own_hooks_directory_is_not_told_about_a_release_record(
    tmp_path: Path,
) -> None:
    # `--root` defaults to `.`, so this gate runs in other people's repositories, and plenty of
    # them have a `hooks/` directory — the first spelling of the guard asked exactly that and
    # told them a record they never had was missing. Asked of the recorded files themselves
    # now. Mutation (declared): probe `hooks/` again -> this reddens.
    root = _repo(tmp_path)
    (root / "hooks").mkdir()
    (root / "hooks" / "hooks.json").write_text("{}\n", encoding="utf-8")
    assert check(root) == []


def test_a_tree_that_ships_every_recorded_file_is_told_when_the_record_is_missing(
    tmp_path: Path,
) -> None:
    # The other direction, and the one DC5 is for: a tree that carries the three files the
    # harness executes is a tree that owes a record of them. Without this the guard above could
    # be narrowed to `if False` and nothing would notice.
    from keelline.release.hashes import HASHED_FILES, RECORD

    root = _repo(tmp_path)
    for relative in HASHED_FILES:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(f"# {relative}\n", encoding="utf-8")
    assert check(root) == [f"{RECORD} is missing; run `keelline release hashes`"]


def test_collect_still_reads_the_package_version_beside_the_repository_constants() -> None:
    # `keelline.REPOSITORY_SLUG` and `keelline.REPOSITORY_URL` (Task 4) sit in
    # `src/keelline/__init__.py` beside `__version__`; `_INIT`'s regex is anchored on
    # `__version__` alone, so the two new lines must not change what this reads.
    from keelline import __version__

    assert collect(ROOT)["src/keelline/__init__.py"] == __version__
