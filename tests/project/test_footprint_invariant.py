"""One invariant for `init`, `upgrade` and `uninstall`, asked of every hostile input at once.

The defect class this module exists for was found four times on one branch, one instance per
review round: a write or removal landing on a file whose bytes the committer does not control
and git does not show — `.git/…`, `.keelline/local/attach.json` through `[paths]`, any
git-ignored file through `[paths]`, and another artifact's kept-out-of-git copy through a forged
ledger entry. Each round fixed its instance and argued the boundary in prose, and the next
instance falsified the prose. So the invariant is asserted here instead, over the product of
the repository-authored inputs (committed `keelline.toml`, the manifest, the local ledger a
clone can force-add) and the commands:

- **I1, nothing hidden is clobbered.** After every command, whether it finished or refused,
  each file the case planted where git does not show it — an ignored file, a file under
  `.git/`, Keelline's out-of-git state, another artifact's kept-out-of-git copy — is present
  with the bytes it had, and no file has appeared under `.git/`.
- **I2, the legitimate user is not refused.** The cases git hides for a person's own reasons —
  fixed names in their excludes, a new file at an ignored place, `[artifacts] local`, a
  symlinked directory no value uses, a tracked file matching an ignore pattern — run every
  command to the end. A guard that refuses them is the over-refusal a narrowing round once had
  to take back.
- **I3, the end state is consistent.** After a command that finished, a dry-run `upgrade` of
  the same tree plans nothing and refuses nothing: every artifact the configuration builds is
  at its own place with its own bytes. A copy removed under another artifact's id, or a region
  inserted into another artifact's file, shows up here as a plan that is not empty.

Which inputs are hostile is a claim about provenance: every value below is one a pulled commit
or a force-added file can carry, and none is the machine's own configuration or argv.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

import keelline
from keelline.config.loader import CONFIG_FILE
from keelline.errors import Refusal
from keelline.project.init import init
from keelline.project.uninstall import uninstall
from keelline.project.upgrade import upgrade
from keelline.scaffold import Manifest, digest
from tests.gitfixture import LsRemote, git, needs_git

HEADER = (
    f'[keelline]\nversion = "{keelline.__version__}"\n\n[project]\nname = "widget"\n\n'
    '[ci]\nmode = "none"\n'
)
OURS = "bytes no Keelline build renders\n"
HOOK = "#!/bin/sh\n# the clone's own pre-commit hook\n"
CLAUDE_COPY = ".keelline/local/artifacts/CLAUDE.md"
ATTACH = ".keelline/local/attach.json"


def _forge_roadmap_record(target: str) -> Callable[[Path], None]:
    """A committed manifest record moving `roadmap` onto `target`, stating the digest of the
    bytes the case planted there — what made `uninstall` delete and `upgrade` overwrite them."""

    def forge(root: Path) -> None:
        manifest = Manifest.read(root)
        record = manifest.get("roadmap")
        assert record is not None
        manifest.with_record(replace(record, target=target, sha256=digest(OURS))).write(root)

    return forge


def _forge_cross_id_ledger(root: Path) -> None:
    """A force-added ledger whose one entry sits under `roadmap`, naming `claude-md`'s copy with
    the digest of its unedited, and so predictable, bytes."""
    copy = root / CLAUDE_COPY
    ledger = {"format": 1, "artifacts": {"roadmap": {CLAUDE_COPY: digest(copy.read_text())}}}
    (root / ".keelline" / "local" / "artifacts.json").write_text(json.dumps(ledger))


@dataclass(frozen=True)
class Case:
    """One configuration of repository-authored inputs, and what git hides around it."""

    name: str
    paths: Mapping[str, str] = field(default_factory=dict)
    local: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    # Hidden files the case plants, root-relative, with their text. Every one is held to I1.
    plant: Mapping[str, str] = field(default_factory=dict)
    # Files `init` itself leaves where git does not show them, also held to I1.
    keep: tuple[str, ...] = ()
    links: Mapping[str, str] = field(default_factory=dict)
    track: tuple[str, ...] = ()
    forge: Callable[[Path], None] | None = None
    # For a legitimate case, the commands that must finish, in order.
    finishes: tuple[str, ...] = ("init", "upgrade", "uninstall")

    def document(self, *, with_paths: bool) -> str:
        text = HEADER
        if self.local:
            listed = ", ".join(f'"{name}"' for name in self.local)
            text += f"\n[artifacts]\nlocal = [{listed}]\n"
        if with_paths and self.paths:
            text += "\n[paths]\n" + "".join(f'{k} = "{v}"\n' for k, v in self.paths.items())
        return text


HOSTILE = [
    Case(
        "region-into-an-ignored-file",
        paths={"agents_md": ".env"},
        ignore=(".env",),
        plant={".env": OURS},
    ),
    Case(
        "forged-record-at-an-ignored-file",
        paths={"roadmap": "build/marker.txt"},
        ignore=("build/",),
        plant={"build/marker.txt": OURS},
        forge=_forge_roadmap_record("build/marker.txt"),
    ),
    Case("region-into-git-s-hook", paths={"agents_md": ".git/hooks/pre-commit"}),
    Case("region-into-git-s-hook-case-folded", paths={"agents_md": ".GIT/hooks/pre-commit"}),
    Case(
        "region-into-git-s-hook-through-a-symlink",
        paths={"agents_md": "gitlink/hooks/pre-commit"},
        links={"gitlink": ".git"},
    ),
    Case("region-into-attach-s-ledger", paths={"agents_md": ATTACH}, plant={ATTACH: OURS}),
    Case(
        "region-into-attach-s-ledger-case-folded",
        paths={"agents_md": ".Keelline/local/attach.json"},
        plant={ATTACH: OURS},
    ),
    Case(
        "region-into-attach-s-ledger-through-a-symlink",
        paths={"agents_md": "hidden/attach.json"},
        plant={ATTACH: OURS},
        links={"hidden": ".keelline/local"},
    ),
    Case(
        "region-into-another-artifact-s-hidden-copy",
        paths={"agents_md": CLAUDE_COPY},
        local=("claude-md",),
        keep=(CLAUDE_COPY,),
    ),
    Case(
        "cross-id-ledger-entry",
        local=("claude-md",),
        keep=(CLAUDE_COPY,),
        forge=_forge_cross_id_ledger,
    ),
]

# Every value that defaults under `docs/`, moved off it, so a symlinked `docs` is on no path.
MOVED_OFF_DOCS = {
    "architecture": "planning/architecture",
    "runbooks": "planning/runbooks",
    "adr": "planning/adr",
    "specs": "planning/specs",
    "plans": "planning/plans",
    "bugs": "planning/bugs",
    "bug_index": "planning/bug-reports.md",
    "roadmap": "planning/roadmap.md",
    "roadmap_history": "planning/roadmap-history.md",
    "memory": "planning/memory",
    "keelline": "planning/keelline",
}

LEGITIMATE = [
    Case("fixed-names-in-the-clone-s-excludes", exclude=("CLAUDE.md", "AGENTS.md")),
    Case(
        "a-new-file-at-an-ignored-place",
        paths={"agents_md": "private/AGENTS.md"},
        ignore=("private/",),
        # Not `uninstall`: it refuses to remove a file at an ignored place a `[paths]` value
        # chose, by design, and names the remedy (take the key out); `test_ignored.py` holds that.
        finishes=("init", "upgrade"),
    ),
    Case("artifacts-kept-out-of-git", local=("claude-md", "roadmap")),
    Case(
        "a-symlinked-directory-no-value-uses",
        paths=MOVED_OFF_DOCS,
        links={"docs": "planning"},
    ),
    Case(
        "a-tracked-file-matching-an-ignore-pattern",
        paths={"agents_md": "notes/AGENTS.md"},
        ignore=("notes/",),
        plant={"notes/AGENTS.md": "# Our notes\n"},
        track=("notes/AGENTS.md",),
    ),
]


def _git_files(root: Path) -> set[str]:
    # `index` and lock files are git's own bookkeeping, rewritten by any `git` call the commands
    # make; everything else appearing under `.git/` was written by something else.
    git_dir = root / ".git"
    return {
        p.relative_to(git_dir).as_posix()
        for p in git_dir.rglob("*")
        if p.is_file() and p.name != "index" and not p.name.endswith(".lock")
    }


def _surround(root: Path, case: Case) -> None:
    """What the clone and the person hold around the configuration: ignore rules, excludes,
    planted hidden files, symlinks, force-tracked files."""
    if case.ignore:
        gitignore = root / ".gitignore"
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        gitignore.write_text(existing + "".join(f"{line}\n" for line in case.ignore))
    if case.exclude:
        exclude = root / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("".join(f"{line}\n" for line in case.exclude))
    (root / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
    (root / ".git" / "hooks" / "pre-commit").write_text(HOOK)
    for relative, text in case.plant.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    for name, target in case.links.items():
        (root / target).mkdir(parents=True, exist_ok=True)
        (root / name).symlink_to(target, target_is_directory=True)
    for relative in case.track:
        git(root, "add", "-f", "--", relative)


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "widget"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@github.com:owner/widget.git")
    (root / "README.md").write_text("# widget\n")
    return root


def _run(command: str, root: Path, tmp_path: Path, *, dry_run: bool = False) -> object:
    machine = tmp_path / "absent.toml"
    if command == "init":
        return init(root, machine=machine, runner=LsRemote(), yes=True, dry_run=dry_run, ci=False)
    if command == "upgrade":
        return upgrade(root, machine=machine, runner=LsRemote(), dry_run=dry_run, force=())
    return uninstall(root, machine=machine, dry_run=dry_run, force=())


def _hidden(root: Path, case: Case, command: str) -> dict[str, bytes]:
    # A force-tracked file is not hidden: git shows every change to it. Keelline's own copies are
    # held only while the command is not `uninstall`, whose job is to remove them.
    held = {".git/hooks/pre-commit", *case.plant} - set(case.track)
    if command != "uninstall":
        held |= set(case.keep)
    return {relative: (root / relative).read_bytes() for relative in held}


def _assert_invariant(
    root: Path, tmp_path: Path, hidden: Mapping[str, bytes], git_before: set[str], *, done: str
) -> None:
    # I1, whatever the command's outcome.
    clobbered = {
        relative
        for relative, data in hidden.items()
        if not (root / relative).is_file() or (root / relative).read_bytes() != data
    }
    assert clobbered == set(), f"I1: hidden files changed or removed: {sorted(clobbered)}"
    appeared = _git_files(root) - git_before
    assert appeared == set(), f"I1: files appeared under .git/: {sorted(appeared)}"
    # I3, after a command that finished and left a footprint behind.
    if done in ("init", "upgrade"):
        try:
            report = _run("upgrade", root, tmp_path, dry_run=True)
        except Refusal as refused:
            pytest.fail(f"I3: a dry-run upgrade after a finished {done} refused: {refused}")
        planned = [
            (a.artifact_id, str(a.verb), a.target)
            for a in report.footprint.actions  # type: ignore[attr-defined]
        ]
        assert planned == [], f"I3: a finished {done} left work for the next upgrade: {planned}"


@needs_git
@pytest.mark.parametrize(
    ("case", "command"),
    [
        pytest.param(case, command, id=f"{case.name}-{command}")
        for case in HOSTILE
        for command in ("init", "upgrade", "uninstall")
        if not (command == "init" and case.forge is not None)
        # `init` cannot meet a hidden copy it has not written yet.
        and not (command == "init" and case.keep)
    ],
)
def test_no_hostile_input_reaches_a_file_git_hides(
    tmp_path: Path, case: Case, command: str
) -> None:
    """I1 and I3 for every hostile case, at every command that can meet it; a refusal passes as
    long as it wrote nothing hidden. At `init` the hostile configuration is there from the
    start, as in a fresh clone; at `upgrade` and `uninstall` a pull brings it into a tree `init`
    already set up."""
    root = _repository(tmp_path)
    if command == "init":
        (root / CONFIG_FILE).write_text(case.document(with_paths=True))
        _surround(root, case)
    else:
        (root / CONFIG_FILE).write_text(case.document(with_paths=False))
        _run("init", root, tmp_path)
        _surround(root, case)
        (root / CONFIG_FILE).write_text(case.document(with_paths=True))
        if case.forge is not None:
            case.forge(root)
    hidden = _hidden(root, case, command)
    git_before = _git_files(root)
    try:
        _run(command, root, tmp_path)
    except Refusal:
        done = ""
    else:
        done = command
    _assert_invariant(root, tmp_path, hidden, git_before, done=done)


@needs_git
@pytest.mark.parametrize("case", [pytest.param(c, id=c.name) for c in LEGITIMATE])
def test_the_legitimate_user_runs_every_command_to_the_end(tmp_path: Path, case: Case) -> None:
    """I2, with I1 and I3 after each step: every command the case lists finishes."""
    root = _repository(tmp_path)
    (root / CONFIG_FILE).write_text(case.document(with_paths=True))
    _surround(root, case)
    for command in case.finishes:
        hidden = _hidden(root, case, command)
        git_before = _git_files(root)
        try:
            _run(command, root, tmp_path)
        except Refusal as refused:
            pytest.fail(f"I2: {command} refused a legitimate configuration: {refused}")
        _assert_invariant(root, tmp_path, hidden, git_before, done=command)
