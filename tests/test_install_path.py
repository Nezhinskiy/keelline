"""The owner's walkthrough (§4), offline, in a temporary directory.

Every wave tested its own package against stubs. This is the one test that runs them in the
order a person does, and it exists because the four packages' seams — the machine file, the
overlay root, the project record, the link tree, the ignore region — are each written by one
package and read by another, and a stub on both sides of a seam agrees with itself.

**Every step runs the real launcher** (D4). Each one used to call a library function, so the
argv wiring of eight commands — the flag names, the `--yes` gate reached through argparse, the
`--machine` refusal from a pipe, the JSON `doctor` prints — was exercised by nothing that ran
them in order. `_cli` below runs `scripts/keelline` in a subprocess, which is how a person and
how a skill reach these commands.

Nothing here touches the network, the real `~`, or any harness binary. `HOME` is a scratch
directory and every harness variable is dropped, and the binaries the CLI resolves through
`PATH` on purpose — `gh`, `claude`, `codex` and `pre-commit`, the owner's own — are answered by
a scratch `bin/` placed first on the subprocess's `PATH`. `pre-commit` there writes the commit
hook `doctor` later asks about, rather than only recording that it was called. `git` is real,
because a repository with no `origin` is not the thing being tested.

**`--machine` is driven through a pseudo-terminal on `attach`/`detach`.** Those two commands
honour it only from an interactive shell and refuse otherwise; `_cli(..., tty=True)` hands the
child a pty as stdin, and one test below proves both halves of that gate through argv.
"""

from __future__ import annotations

import json
import os
import pty
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import keelline
from keelline.config.loader import CONFIG_FILE, load
from keelline.doctor.api import RED, SKIP, run_checks
from keelline.memory.api import DELIMITER, PROJECTS, harness_memory_path, markers
from keelline.runner import Completed
from tests.snapshot import (
    assert_snapshot_changed,
    assert_snapshot_unchanged,
    git,
    snapshot,
)

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
    """A `Runner` that records argv and reaches no binary.

    The one test in this module that still calls `run_checks` in this process needs a runner to
    hand it, and `ci-ref` — the only row that would use one — skips on this fixture. Everything
    else here reaches the CLI's own `subprocess_runner()` through the launcher, and the fakes
    `_fake_binaries` writes are what answer it.
    """

    calls: list[list[str]] = field(default_factory=list)

    def run(self, argv: list[str], cwd: Path) -> Completed:
        self.calls.append(argv)
        return Completed(0, "", "")


def _project(tmp_path: Path, *, mode: str) -> Path:
    root = tmp_path / "project"
    root.mkdir(parents=True, exist_ok=True)
    (root / CONFIG_FILE).write_text(
        CONFIG.format(version=keelline.__version__, project=PROJECT, mode=mode), encoding="utf-8"
    )
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", ORIGIN)
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
    bin: Path


def _fake_binaries(bin_dir: Path) -> None:
    """The four binaries the CLI resolves through `PATH`, as the walkthrough may see them.

    `pre-commit install` writes the hook `doctor` later asks about, so the fake writes it too —
    a stub that answered 0 and wrote nothing would make two steps disagree for no reason a
    reader could see (the `_Harness` runner this replaces said the same). `gh` must never be
    reached on the `--local` path, so its fake exits 1 and the test asserts the log never names
    it. `claude` and `codex` are here because `setup` installs the preset's plugins through
    `subprocess_runner()`, which resolves them on `PATH`: the plan's own list named only the
    first two, and without these the walkthrough would run the developer's real harness CLI,
    which the Global Constraints forbid outright. Nothing later reads their effect, so they
    record and exit 0.
    """
    bin_dir.mkdir()
    log = bin_dir / "calls.log"
    (bin_dir / "pre-commit").write_text(
        "#!/bin/sh\n"
        f'printf \'%s\\n\' "pre-commit $*" >> "{log}"\n'
        "mkdir -p .git/hooks && printf '#!/bin/sh\\nexit 0\\n' > .git/hooks/pre-commit\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "gh").write_text(
        f'#!/bin/sh\nprintf \'%s\\n\' "gh $*" >> "{log}"\nexit 1\n', encoding="utf-8"
    )
    for harness in ("claude", "codex"):
        (bin_dir / harness).write_text(
            f'#!/bin/sh\nprintf \'%s\\n\' "{harness} $*" >> "{log}"\nexit 0\n',
            encoding="utf-8",
        )
    for name in ("pre-commit", "gh", "claude", "codex"):
        (bin_dir / name).chmod(0o755)


def _cli(walk: Walkthrough, *argv: str, tty: bool = False) -> subprocess.CompletedProcess[str]:
    """One command, the way a person or a skill runs it: the launcher, argv, a pipe or a tty.

    `tty=True` hands the child a pseudo-terminal as stdin, which is what `attach --machine`
    and `detach --machine` require (they refuse from a pipe, and the test proves the pipe
    refusal separately). Nothing here reads the developer's own `~`: `HOME` is the scratch
    home and every harness variable is dropped.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("CLAUDE_", "PLUGIN_", "KEELLINE_", "XDG_"))
    }
    env["HOME"] = str(walk.home)
    env["PATH"] = f"{walk.bin}{os.pathsep}{env.get('PATH', '')}"
    env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
    env["CLAUDE_PLUGIN_DATA"] = str(walk.data)
    command = [sys.executable, str(ROOT / "scripts" / "keelline"), *argv]
    if not tty:
        return subprocess.run(
            command,
            cwd=walk.root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    parent, child = pty.openpty()
    try:
        return subprocess.run(
            command,
            cwd=walk.root,
            stdin=child,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
    finally:
        os.close(child)
        os.close(parent)


def _doctor(walk: Walkthrough, *, root: Path | None = None) -> list[dict[str, str]]:
    """The fifteen rows, read back out of what `doctor --json` printed on the launcher's stdout."""
    done = _cli(
        walk,
        "doctor",
        "--json",
        "--root",
        str(walk.root if root is None else root),
        "--home",
        str(walk.home),
        "--machine",
        str(walk.machine),
    )
    assert done.stdout, done.stderr
    rows: list[dict[str, str]] = json.loads(done.stdout)["checks"]
    assert len(rows) == 15, rows
    return rows


def _install_path(tmp_path: Path) -> Walkthrough:
    """Steps 1-5: the overlay, the machine layer, a repository, attach, and a note in it.

    Every step is the real launcher with the real argv (D4). Step 1's overlay is created
    **outside** the project root on purpose: `setup` refuses to record one inside it (R13/R14),
    because a path inside the project is exactly the shape of tree a hostile clone can ship.
    """
    home = tmp_path / "home"
    data = tmp_path / "plugin-data"
    machine = tmp_path / "config" / "keelline" / "config.toml"
    machine.parent.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    _fake_binaries(bin_dir)

    root = _project(tmp_path, mode="overlay")
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    # Where `overlay create --root <overlays> --name keelline-private` puts it, which
    # `overlay.create.target_root` computes from the arguments alone.
    overlay = overlays / "keelline-private"
    store = overlay / PROJECTS / PROJECT / "memory"
    walk = Walkthrough(root, overlay, machine, home, data, store, bin_dir)

    def step(*argv: str, tty: bool = False) -> subprocess.CompletedProcess[str]:
        done = _cli(walk, *argv, tty=tty)
        assert done.returncode == 0, f"`{' '.join(argv)}`: {done.stderr}"
        return done

    # 1. the overlay, rendered from the shipped template with no network call.
    step(
        "overlay",
        "create",
        "--owner",
        OWNER,
        "--name",
        "keelline-private",
        "--local",
        "--root",
        str(overlays),
    )
    # 2. make it this owner's, and install its commit-time secret scan.
    step("overlay", "init", "--owner", OWNER, "--root", str(overlay))
    # 3. the machine layer, into a scratch machine file and a scratch home. **Two runs**, as
    # the walkthrough had before it was converted: the first writes the machine file with no
    # overlay in it, the second records one into a file that already exists. "A second `setup`
    # records an overlay the first did not" is a merge seam between two lanes, and collapsing
    # the two runs into one would have left it to `tests/setup/` alone -- which is the shape of
    # gap this whole module exists to close. The assertion between them is what makes it a
    # seam rather than two commands that happened to run.
    step(
        "setup",
        "--preset",
        "recommended",
        "--home",
        str(home),
        "--machine",
        str(machine),
        "--root",
        str(root),
    )
    assert str(overlay) not in machine.read_text(encoding="utf-8"), (
        "the first `setup` named no overlay and must have recorded none"
    )
    step(
        "setup",
        "--preset",
        "recommended",
        "--home",
        str(home),
        "--machine",
        str(machine),
        "--overlay",
        str(overlay),
        "--root",
        str(root),
    )
    assert str(overlay) in machine.read_text(encoding="utf-8"), (
        "the second `setup` recorded the overlay into the file the first one wrote"
    )
    # 4. attach: the diff first, then the write. `--check` writes nothing and prints what the
    # `--yes` run is consenting to, which is the order the attach skill walks.
    previewed = step(
        "attach", "--store", str(store), "--check", "--machine", str(machine), tty=True
    )
    assert previewed.stdout.strip(), "`attach --check` printed no diff to consent to"
    step("attach", "--store", str(store), "--yes", "--machine", str(machine), tty=True)

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
    return walk


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
    # The fakes on `PATH` were what ran, and `gh` was not among them: `--local` renders the
    # shipped template and touches no network, so a `gh` line here would mean the walkthrough
    # took the `--template` branch and only looked as if it had not.
    calls = (walk.bin / "calls.log").read_text(encoding="utf-8").splitlines()
    assert "pre-commit install" in calls
    assert not [line for line in calls if line.startswith("gh ")], calls


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
    bin_dir = tmp_path / "bin"
    _fake_binaries(bin_dir)
    walk = Walkthrough(root, root, machine, tmp_path / "home", tmp_path / "data", notes, bin_dir)
    trusted = _cli(walk, "memory", "trust", "--in-repo-memory", "--machine", str(machine))
    assert trusted.returncode == 0, trusted.stderr
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


def test_detach_returns_the_project_to_where_it_started(tmp_path: Path) -> None:
    # The round trip over the whole path rather than over `attach`'s own ledger: snapshot every
    # file under the project root before the attach and compare after the detach. What the
    # overlay records is deliberately not on this list — `projects/<name>/project.toml` is the
    # owner's consent (§6.2) and outlives a detach on purpose.
    #
    # The walkthrough's own steps are repeated here rather than reused, because the snapshot has
    # to be taken between `setup` and `attach` and `_install_path` runs both.
    home = tmp_path / "home"
    machine = tmp_path / "config" / "keelline" / "config.toml"
    machine.parent.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    _fake_binaries(bin_dir)
    root = _project(tmp_path, mode="overlay")
    overlays = tmp_path / "overlays"
    overlays.mkdir()
    overlay = overlays / "keelline-private"
    store = overlay / PROJECTS / PROJECT / "memory"
    walk = Walkthrough(root, overlay, machine, home, tmp_path / "plugin-data", store, bin_dir)

    def step(*argv: str, tty: bool = False) -> None:
        done = _cli(walk, *argv, tty=tty)
        assert done.returncode == 0, f"`{' '.join(argv)}`: {done.stderr}"

    step(
        "overlay",
        "create",
        "--owner",
        OWNER,
        "--name",
        "keelline-private",
        "--local",
        "--root",
        str(overlays),
    )
    step("overlay", "init", "--owner", OWNER, "--root", str(overlay))
    step(
        "setup",
        "--preset",
        "recommended",
        "--home",
        str(home),
        "--machine",
        str(machine),
        "--overlay",
        str(overlay),
        "--root",
        str(root),
    )
    before = snapshot(root)
    # The mutation guard the Global Constraints ask for: `snapshot` is a walk, so the
    # comparison below passes vacuously the day the walk stops finding anything.
    assert before
    step("attach", "--store", str(store), "--yes", "--machine", str(machine), tty=True)
    assert_snapshot_changed(root, before)
    step("detach", "--machine", str(machine), tty=True)
    assert_snapshot_unchanged(root, before)
    # Stated rather than left to the file walk: `detach_main` withdraws the links and not the
    # directory that held them, because "withdrawing a link is not licence to delete a
    # directory". What is left is empty, and this is where that is written down.
    assert list((root / "docs" / "memory").iterdir()) == []


def test_doctor_is_green_on_the_attached_fixture(tmp_path: Path) -> None:
    # Green meaning: no `red`, and the only `skip`s are the three this build cannot answer —
    # the release's recorded hashes, the Codex hook-trust hash §10 lists as unmeasured, and a
    # `[ci] ref` that `init` will write.
    walk = _install_path(tmp_path)
    rows = _doctor(walk)
    assert [row["name"] for row in rows if row["status"] == RED] == []
    assert [row["name"] for row in rows if row["status"] == SKIP] == [
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
    # goes through `keelline.runner.Runner`, which the stub below answers, and it is the only
    # one that would leave the machine.
    #
    # **The one test here that keeps the library seam**, and the reason is the measurement
    # itself: this counts launches through a `Popen` patched in *this* process, and a `doctor`
    # run as a subprocess launches its four in a process no patch of ours can see. Everything
    # else in this module runs the launcher (D4); this cannot, and says so.
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
    attached = next(row for row in _doctor(walk) if row["name"] == "attached")
    assert attached["status"] == RED
    assert "real directory" in attached["detail"]


def test_attach_refuses_machine_from_a_pipe_and_honours_it_from_a_terminal(tmp_path: Path) -> None:
    # The interactive-shell gate on `--machine`, reached through argv rather than through the
    # `interactive=` seam: a pipe is refused with exit 2 and the sentence, a pseudo-terminal
    # is honoured. The library-level tests prove the seam; this proves the launcher hands
    # the command a stdin the gate can ask. No mutation of its own — the gate's own entry in
    # mutations.toml (attach/commands.py) reddens the library test and, through this, the
    # pipe half here; run it and say so.
    walk = _install_path(tmp_path)
    store = str(walk.overlay / PROJECTS / PROJECT / "memory")
    piped = _cli(walk, "attach", "--store", store, "--check", "--machine", str(walk.machine))
    assert piped.returncode == 2 and "interactive shell" in piped.stderr
    tty = _cli(
        walk, "attach", "--store", store, "--check", "--machine", str(walk.machine), tty=True
    )
    assert tty.returncode == 0, tty.stderr
