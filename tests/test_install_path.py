"""The owner's walkthrough (§4), offline, in a temporary directory.

Every wave tested its own package against stubs. This is the one test that runs them in the
order a person does, and it exists because the four packages' seams — the machine file, the
overlay root, the project record, the link tree, the ignore region — are each written by one
package and read by another, and a stub on both sides of a seam agrees with itself.

Nothing here touches the network, the real `~`, or any harness binary. `gh`, `claude`, `codex`
and `pre-commit` reach the `Runner` stub below, which models the one effect `attach` goes on to
read — the commit hook `pre-commit install` writes — rather than only recording that it was
called. `git` is real, because a repository with no `origin` is not the thing being tested.

**`--machine` is driven as a parameter and never as a CLI flag on `attach`/`detach`.** Those two
commands honour it only from an interactive shell and refuse otherwise, and pytest has no tty;
the library functions take `machine=` for exactly this reason.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import keelline
from keelline.attach.api import attach, detach
from keelline.cli import build_parser, discover_registrars, run
from keelline.config.loader import CONFIG_FILE, load
from keelline.doctor.api import RED, SKIP, run_checks
from keelline.memory.api import DELIMITER, PROJECTS, harness_memory_path, markers
from keelline.overlay.api import Completed, create
from keelline.setup.api import setup

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "hooks" / "run-hook.sh"
OWNER = "owner"
PROJECT = "widget"
ORIGIN = f"git@github.com:{OWNER}/{PROJECT}.git"
# The rule the walkthrough puts in the overlay and then asks a session for. Distinctive enough
# that finding it in the wrapper's stdout cannot be an accident.
RULE_BODY = "NEVER FORCE-PUSH A SHARED BRANCH; open a pull request instead."

CONFIG = """[keelline]
version = "{version}"
state = "installed"

[project]
name = "{project}"

[memory]
mode = "{mode}"
groups = ["developer", "project-stable"]
"""


@dataclass
class _Harness:
    """A `Runner` that records argv and models the one effect a later step reads.

    Recording alone would be a stub that agrees with itself: `attach` runs `pre-commit install`
    and `doctor` then asks whether the overlay's commit hook is there, so a runner that answers
    0 and writes nothing makes those two steps disagree for no reason a reader could see.
    """

    calls: list[list[str]] = field(default_factory=list)

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        if argv[:2] == ["pre-commit", "install"]:
            hook = cwd / ".git" / "hooks" / "pre-commit"
            hook.parent.mkdir(parents=True, exist_ok=True)
            hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        return Completed(0, "", "")


def _git(root: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
    }
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, env=env)


def _project(tmp_path: Path, *, mode: str) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    (root / CONFIG_FILE).write_text(
        CONFIG.format(version=keelline.__version__, project=PROJECT, mode=mode), encoding="utf-8"
    )
    _git(root, "init", "-q", "-b", "main")
    _git(root, "remote", "add", "origin", ORIGIN)
    return root


@dataclass(frozen=True)
class Walkthrough:
    """What §4's eleven steps leave behind, so each test can assert about one of them."""

    root: Path
    overlay: Path
    machine: Path
    home: Path
    data: Path
    store: Path
    runner: _Harness


def _install_path(tmp_path: Path) -> Walkthrough:
    """Steps 1-5: setup, overlay, a repository, attach, and a note in the overlay.

    Step 2's overlay is created **outside** the project root on purpose: `setup` refuses to
    record one inside it (R13/R14), because a path inside the project is exactly the shape of
    tree a hostile clone can ship.
    """
    home = tmp_path / "home"
    data = tmp_path / "plugin-data"
    machine = tmp_path / "config" / "keelline" / "config.toml"
    machine.parent.mkdir(parents=True)
    runner = _Harness()

    root = _project(tmp_path, mode="overlay")

    # 1. the machine layer, into a scratch machine file and a scratch home.
    first = setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=root,
    )
    assert first.machine_written

    # 2. the overlay, rendered from the shipped template with no network call; `setup` records it.
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    created = create(OWNER, "keelline-private", source="local", root=overlays, runner=runner)
    second = setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=str(created.root),
        project_root=root,
    )
    assert second.overlay is not None

    # 4. attach: the binding record, the ignore region, the ledger, the link tree.
    store = created.root / PROJECTS / PROJECT / "memory"
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=True,
        runner=runner,
        home=home,
    )

    # 5. a standing rule in this project's own share of the overlay.
    #
    # `project-stable` and not `developer`: `memory.store.COMMON_GROUP` is `developer`, so that
    # name resolves to `<overlay>/common/memory`, which is shared across every project. A note
    # written under `projects/<name>/memory/developer/` is linked by nothing and arrives
    # nowhere — which is the seam this walkthrough found first.
    note = store / "project-stable" / "no-force-push.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\nname: no-force-push\ndescription: never force-push a shared branch\n"
        f"metadata:\n  type: rule\n  startup: 1\n---\n\n{RULE_BODY}\n",
        encoding="utf-8",
    )
    return Walkthrough(root, created.root, machine, home, data, store, runner)


def _session(walk: Walkthrough, *argv: str) -> subprocess.CompletedProcess[str]:
    """One `hooks.json` entry, run the way a harness runs it: through the wrapper, raw.

    `HOME` and `--machine` both point into the scratch tree, so nothing here can read the
    developer's own `~/.claude` or `~/.config/keelline`.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CLAUDE_", "PLUGIN_", "KEELLINE_", "XDG_"))
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
    env["CLAUDE_PROJECT_DIR"] = str(walk.root)
    env["CLAUDE_PLUGIN_DATA"] = str(walk.data)
    env["HOME"] = str(walk.home)
    return subprocess.run(
        [str(WRAPPER), "open", *argv, "--machine", str(walk.machine)],
        cwd=walk.root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _bundle(walk: Walkthrough, bundle: str, part: int = 1) -> subprocess.CompletedProcess[str]:
    return _session(walk, "memory", "session-context", "--bundle", bundle, "--part", str(part))


def _doctor_env(walk: Walkthrough) -> dict[str, str]:
    """The environment a harness session has: a data root, and neither ignored variable."""
    # `HOME` is here because `doctor`'s `wrapper` check hands this environment to a real
    # subprocess: without it the wrapper's `keelline --version` builds the default machine path
    # out of the developer's own home directory, which is a read this suite does not make.
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(walk.home),
        "CLAUDE_PLUGIN_ROOT": str(ROOT),
        "CLAUDE_PLUGIN_DATA": str(walk.data),
    }


def test_setup_then_overlay_then_attach_then_a_session_sees_memory(tmp_path: Path) -> None:
    # The whole path, in the order a person walks it, ending where it is supposed to end: the
    # rule the owner wrote in their overlay arrives in a session's context.
    #
    # RAW, with no JSON envelope, which is the invariant DP1 turns on: `memory
    # session-context` prints the text itself, so `bundles.CAP_MARGIN` is additive rather than
    # fighting an envelope's own escaping.
    walk = _install_path(tmp_path)
    done = _bundle(walk, "standing-rules")
    assert done.returncode == 0, done.stderr
    assert RULE_BODY in done.stdout
    assert not done.stdout.lstrip().startswith("{")
    assert '"summary"' not in done.stdout


def test_the_machine_file_is_the_only_thing_that_says_where_the_overlay_is(
    tmp_path: Path,
) -> None:
    # DP2, end to end. `setup` wrote the root and `attach` read it back; nothing on a command
    # line chose it. The vacuity guard for the walkthrough above: a session that resolved a
    # store without the machine file would pass that test for the wrong reason.
    walk = _install_path(tmp_path)
    assert str(walk.overlay) in walk.machine.read_text(encoding="utf-8")
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CLAUDE_", "PLUGIN_", "KEELLINE_", "XDG_"))
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
    env["CLAUDE_PROJECT_DIR"] = str(walk.root)
    env["HOME"] = str(walk.home)
    without = subprocess.run(
        [str(WRAPPER), "open", "memory", "session-context", "--bundle", "standing-rules"],
        cwd=walk.root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert RULE_BODY not in without.stdout
    # Non-vacuous: the run has to fail for *this* reason, and not for any other. The
    # wrapper degrades open, so the exit code says nothing and stderr says everything.
    assert "no overlay root is recorded" in without.stderr


def test_the_bundle_arrives_whole_and_within_the_platform_cap(tmp_path: Path) -> None:
    # The end-to-end form of the invariant that reversed DP1: what one `hooks.json` entry emits
    # must fit the platform's own cap, because anything above it is truncated by the harness and
    # a truncated block is a block that arrives half-said.
    #
    # The plan asks for `trust.wrap`'s two region markers here. In **overlay** mode there are
    # none and there must not be: the notes are the machine owner's own, `inside_project` is
    # False by construction and `bundles.blocks` wraps nothing — so that assertion cannot hold
    # on this walkthrough, and the mode where it does hold is the test below.
    walk = _install_path(tmp_path)
    done = _bundle(walk, "standing-rules")
    config = load(walk.root, machine=walk.machine)
    assert done.stdout
    assert len(done.stdout) <= config.native_caps.hook_output_chars
    assert DELIMITER not in done.stdout


def test_a_wrapped_bundle_arrives_with_both_of_its_region_markers(tmp_path: Path) -> None:
    # `trust.wrap` puts the closing nonce at the very end, so any truncation of the emitted
    # string drops it — and a region that opens and never closes is the defeat of the one
    # delimiter this project built as its boundary. It was measured arriving that way once, and
    # this is the end-to-end assertion that it does not.
    #
    # `in-repo` mode, because that is the mode in which a store is repository data and a region
    # is what wraps it. Same wrapper, same command, same scratch machine file.
    root = _project(tmp_path, mode="in-repo")
    machine = tmp_path / "config" / "keelline" / "config.toml"
    machine.parent.mkdir(parents=True)
    notes = root / "docs" / "memory" / "project-stable"
    notes.mkdir(parents=True)
    (notes / "no-force-push.md").write_text(
        "---\nname: no-force-push\ndescription: never force-push a shared branch\n"
        f"metadata:\n  type: rule\n  startup: 1\n---\n\n{RULE_BODY}\n",
        encoding="utf-8",
    )
    code = run(
        [
            "memory",
            "trust",
            "--in-repo-memory",
            "--root",
            str(root),
            "--machine",
            str(machine),
        ],
        parser=build_parser(discover_registrars()),
    )
    assert code == 0
    walk = Walkthrough(root, root, machine, tmp_path / "home", tmp_path / "data", notes, _Harness())
    done = _bundle(walk, "standing-rules")
    assert done.returncode == 0, done.stderr
    assert RULE_BODY in done.stdout
    found = re.search(rf"{re.escape(DELIMITER)}:([0-9a-f]+)>>>", done.stdout)
    assert found is not None, done.stdout
    begin, end = markers(found.group(1))
    assert begin in done.stdout
    assert end in done.stdout
    config = load(root, machine=machine)
    assert len(done.stdout) <= config.native_caps.hook_output_chars


# The only `.git` paths a defect this guard cares about could actually land in: a hook dropped
# into `.git/hooks/`, a rule written to `.git/config`, an ignore region added to
# `.git/info/exclude`. Everything else under `.git` — `objects/`, `logs/`, `refs/`, a fresh
# `commit-graph`, a pack, `gc.log`, `objects/maintenance.lock` — is git's own background
# bookkeeping. The fixtures that build these repositories pin `GIT_CONFIG_GLOBAL` and
# `GIT_CONFIG_SYSTEM` to `os.devnull`, which leaves `gc.auto` and `maintenance.auto` at their
# defaults, so that bookkeeping can run — and does — between two snapshots taken moments apart.
_STABLE_GIT_FILES = (Path("config"), Path("info") / "exclude")


def _stable_git_snapshot(root: Path) -> dict[str, bytes]:
    """The narrow slice of `.git` this guard reads: the two named files, plus every file
    under `hooks/`, by path relative to `root`."""
    git = root / ".git"
    files: dict[str, bytes] = {}
    for relative in _STABLE_GIT_FILES:
        candidate = git / relative
        if candidate.is_file():
            files[str(Path(".git") / relative)] = candidate.read_bytes()
    hooks = git / "hooks"
    if hooks.is_dir():
        for path in sorted(hooks.iterdir()):
            if path.is_file():
                files[str(Path(".git") / "hooks" / path.name)] = path.read_bytes()
    return files


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every regular file under the root, by relative path.

    `.git` is included deliberately — this is the walk that would catch an ignore region
    written to `.git/info/exclude` or a hook dropped into `.git/hooks` — but narrowed to the
    paths a defect could actually land in. See `_stable_git_snapshot` for why the rest of
    `.git` is pruned rather than walked: it is a moving target, not a place this guard watches.
    """
    files: dict[str, bytes] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        if current == root:
            dirnames[:] = [name for name in dirnames if name != ".git"]
        for name in filenames:
            path = current / name
            if path.is_file():
                files[str(path.relative_to(root))] = path.read_bytes()
    files.update(_stable_git_snapshot(root))
    return files


def _describe_snapshot_diff(before: dict[str, bytes], after: dict[str, bytes]) -> str:
    """A failure message a person can read: which paths came, went or changed, not a dump of
    every file's bytes — which is what the bare `dict == dict` assertion this backs used to
    print, `.git` object tree included, on the one CI job the race actually hit.
    """
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(path for path in before.keys() & after.keys() if before[path] != after[path])
    return f"snapshot differs: added={added} removed={removed} changed={changed}"


def _assert_snapshot_unchanged(root: Path, before: dict[str, bytes]) -> None:
    after = _snapshot(root)
    assert after == before, _describe_snapshot_diff(before, after)


def _assert_snapshot_changed(root: Path, before: dict[str, bytes]) -> dict[str, bytes]:
    after = _snapshot(root)
    assert after != before, "expected at least one file under the root to differ; none did"
    return after


def test_the_narrowed_git_walk_still_catches_a_write_to_each_stable_path(tmp_path: Path) -> None:
    # The non-vacuity guard for the narrowing itself: `_snapshot` no longer walks all of
    # `.git`, and a narrowing that stopped noticing a hook dropped into `.git/hooks/` or an
    # ignore region added to `.git/info/exclude` would be a regression wearing a fix's clothes.
    # Plant a file at each of the three stable spots the review named and require the snapshot
    # to see every one of them, one path at a time.
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    before = _snapshot(root)
    assert before

    (root / ".git" / "info" / "exclude").write_text("/planted-by-a-defect\n", encoding="utf-8")
    after_exclude = _assert_snapshot_changed(root, before)
    assert ".git/info/exclude" in after_exclude

    with (root / ".git" / "config").open("a", encoding="utf-8") as handle:
        handle.write('[planted]\n\tby = "a-defect"\n')
    after_config = _assert_snapshot_changed(root, after_exclude)
    assert ".git/config" in after_config

    hooks = root / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    after_hook = _assert_snapshot_changed(root, after_config)
    assert ".git/hooks/pre-commit" in after_hook


def test_the_narrowed_git_walk_ignores_gits_own_background_bookkeeping(tmp_path: Path) -> None:
    # The defect the review found: `checks (ubuntu-latest, 3.13)` failed because git's own
    # background maintenance dropped `objects/maintenance.lock` between two snapshots, and the
    # old, unrestricted walk over `.git` treated that as a write `attach`/`detach` had made.
    # Plant the same artifacts by hand — a lock file, a gc log, a commit-graph — and require
    # the narrowed walk to stay unaffected by all three.
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    before = _snapshot(root)
    assert before

    objects = root / ".git" / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    (objects / "maintenance.lock").write_bytes(b"")
    (root / ".git" / "gc.log").write_text("warning: there are too many unreachable\n")
    (objects / "info").mkdir(parents=True, exist_ok=True)
    (objects / "info" / "commit-graph").write_bytes(b"CGPH")
    _assert_snapshot_unchanged(root, before)


def test_detach_returns_the_project_to_where_it_started(tmp_path: Path) -> None:
    # The round trip over the whole path rather than over `attach`'s own ledger: snapshot every
    # file under the project root before the attach and compare after the detach. What the
    # overlay records is deliberately not on this list — `projects/<name>/project.toml` is the
    # owner's consent (§6.2) and outlives a detach on purpose.
    home = tmp_path / "home"
    machine = tmp_path / "config" / "keelline" / "config.toml"
    machine.parent.mkdir(parents=True)
    runner = _Harness()
    root = _project(tmp_path, mode="overlay")
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=None,
        project_root=root,
    )
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    created = create(OWNER, "keelline-private", source="local", root=overlays, runner=runner)
    setup(
        "recommended",
        home=home,
        machine=machine,
        runner=runner,
        yes=True,
        overlay=str(created.root),
        project_root=root,
    )
    before = _snapshot(root)
    # The mutation guard the Global Constraints ask for: `_snapshot` is a walk, so the
    # comparison below passes vacuously the day the walk stops finding anything.
    assert before
    attach(
        root,
        store=created.root / PROJECTS / PROJECT / "memory",
        machine=machine,
        confirmed=True,
        trust_remote=True,
        runner=runner,
        home=home,
    )
    _assert_snapshot_changed(root, before)
    detach(root, machine=machine, home=home)
    _assert_snapshot_unchanged(root, before)
    # Stated rather than left to the file walk: `detach_main` withdraws the links and not the
    # directory that held them, because "withdrawing a link is not licence to delete a
    # directory". What is left is empty, and this is where that is written down.
    assert list((root / "docs" / "memory").iterdir()) == []


def test_doctor_is_green_on_the_attached_fixture(tmp_path: Path) -> None:
    # Green meaning: no `red`, and the only `skip`s are the three this build cannot answer —
    # the release's recorded hashes, the Codex hook-trust hash §10 lists as unmeasured, and a
    # `[ci] ref` that `init` will write.
    walk = _install_path(tmp_path)
    checks = run_checks(
        walk.root,
        home=walk.home,
        machine=walk.machine,
        runner=_Harness(),
        env=_doctor_env(walk),
    )
    assert [check.name for check in checks if check.status == RED] == []
    assert [check.name for check in checks if check.status == SKIP] == [
        "files",
        "codex-trust",
        "ci-ref",
    ]


# What `keelline.doctor` says it launches, in `__init__`'s own paragraph and again in
# `docs/cli.md`: four subprocesses on a green attached installation. Written as a number rather
# than as a set of argv lists so the failure reads as "the count moved", which is the claim.
DOCTOR_LAUNCHES = 4


def test_doctor_launches_the_number_of_subprocesses_it_says_it_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `doctor/__init__.py` used to say "exactly two" and the true answer was four: one launch is
    # this area's own — the wrapper probe — and three more come from inside the areas its rows
    # call, where nobody counting `subprocess.run` in `doctor/` would see them. The number had
    # already moved twice during this branch's review before anyone measured it.
    #
    # This case is deliberately brittle. A row that starts asking `git` one more question moves
    # it, and that is the point: the number moving *silently* is the defect this exists for, and
    # a reader who has to update a constant has read the paragraph that states it.
    #
    # `Popen` and not `subprocess.run`: `run` is a wrapper around it, so patching the lower of
    # the two counts a caller that reached past `run` as well. `ci-ref` is not among these — it
    # goes through `overlay.api.Runner`, which the fixture stubs, and it is the only one that
    # would leave the machine.
    walk = _install_path(tmp_path)
    launched: list[list[str]] = []
    real = subprocess.Popen

    def spy(argv, *args, **kwargs):  # type: ignore[no-untyped-def]
        launched.append([str(part) for part in argv])
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spy)
    checks = run_checks(
        walk.root,
        home=walk.home,
        machine=walk.machine,
        runner=_Harness(),
        env=_doctor_env(walk),
    )
    monkeypatch.undo()
    # The report is green first, so a count taken from a run that fell over early cannot pass.
    assert [check.name for check in checks if check.status == RED] == []
    assert len(launched) == DOCTOR_LAUNCHES, launched
    # And they are the four the paragraph names, not four of something else: one wrapper probe,
    # and three `git` questions. Asserted by shape rather than by full argv, because two of the
    # three carry a temporary path.
    assert sum(1 for argv in launched if argv[0] == str(WRAPPER)) == 1
    assert sum(1 for argv in launched if argv[0] == "git") == 3


def test_doctor_is_red_when_the_memory_path_is_a_real_directory(tmp_path: Path) -> None:
    # §12's row, end to end: replace the link with a real directory and assert `attached` goes
    # red. This is the shape one existing checkout already has, which is why the spec names it
    # rather than leaving it to a general "not attached".
    walk = _install_path(tmp_path)
    harness = harness_memory_path(walk.root, walk.home)
    harness.mkdir(parents=True, exist_ok=True)
    checks = run_checks(
        walk.root,
        home=walk.home,
        machine=walk.machine,
        runner=_Harness(),
        env=_doctor_env(walk),
    )
    attached = next(check for check in checks if check.name == "attached")
    assert attached.status == RED
    assert "real directory" in attached.detail
