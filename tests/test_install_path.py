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


def _files(root: Path) -> dict[str, bytes]:
    """Every regular file under the root, by relative path — `.git` included deliberately."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
    before = _files(root)
    # The mutation guard the Global Constraints ask for: `_files` is an `rglob` loop, so the
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
    assert _files(root) != before
    detach(root, machine=machine, home=home)
    assert _files(root) == before
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
