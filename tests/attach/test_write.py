"""What `keelline attach` writes, and the three refusals it owes before it writes anything.

DP3's third rule is here: a write that would widen a permission refuses without an explicit
confirmation. It is a parameter and a `Refusal` rather than a step in a document, because in
this harness the CLI is driven by a model that has read the repository, and a gate enforced by
model compliance is not a gate.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from keelline import fsops
from keelline.attach.api import attach, ledger
from keelline.errors import Failure, Refusal
from keelline.memory.api import PROJECT_RECORD
from keelline.overlay.api import COMMON_CLAUDE, COMMON_CODEX
from keelline.runner import Completed
from keelline.scaffold import Style, extract, owned_ids

# The fixture the binding tests already build, reused rather than copied: one spelling of the
# overlay layout keeps the two modules from drifting apart about what `--store` names.
from tests.attach.test_binding import _git, _machine, _project_and_store

# The walk-based snapshot guard, owned at the top level rather than duplicated here and in
# tests/test_install_path.py: it used to exist twice, verbatim including its docstring, and the
# two copies drifted apart on the one thing that mattered — how much of `.git` to trust.
from tests.snapshot import assert_snapshot_unchanged, snapshot

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

LEDGER = ".keelline/local/attach.json"
SETTINGS = ".claude/settings.local.json"
RULE = "Bash(uv run pytest:*)"
ENTRY = {"type": "command", "command": "echo hello"}


@dataclass
class FakeRunner:
    """Records argv and answers 0, so no test here reaches a real `pre-commit`."""

    calls: list[list[str]] = field(default_factory=list)
    answer: Completed = field(default_factory=lambda: Completed(0, "", ""))

    def run(self, argv: list[str], cwd: Path) -> Completed:
        del cwd
        self.calls.append(argv)
        return self.answer


def _overlay_repository(overlay: Path, *, hooks_path: Path | None = None) -> Path:
    """The overlay as what it actually is — a git repository — and where its hooks live.

    `attach` asks `guards.hooks_dir` rather than assuming `.git/hooks`, so the fixture has to
    be a repository for the question to have an answer. `hooks_path` sets `core.hooksPath`,
    which is an ordinary global dotfiles setting and the arrangement the hardcoded path got
    wrong: the scan reads as missing on every attach and `pre-commit install` is shelled out to
    every time.
    """
    _git(overlay, "init", "-q", "-b", "main")
    if hooks_path is None:
        # Pinned LOCALLY, and this is not belt-and-braces. `hooks_dir` runs `git` under
        # `gitenv.scrubbed_env()`, which keeps `HOME` deliberately — honouring the machine
        # owner's global `core.hooksPath` is exactly what this lane now asks for — so a
        # developer whose own `~/.gitconfig` sets one would have this fixture answer *their*
        # directory and the case fail for a reason that is nothing to do with the code. `_git`
        # pins only `GIT_CONFIG_GLOBAL`, which the separate `hooks_dir` subprocess never sees.
        # Local config outranks global, so the fixture says what it means and production is
        # untouched.
        own = overlay / ".git" / "hooks"
        _git(overlay, "config", "core.hooksPath", str(own))
        return own
    hooks_path.mkdir(parents=True, exist_ok=True)
    _git(overlay, "config", "core.hooksPath", str(hooks_path))
    return hooks_path


def _overlay_grants(
    store: Path,
    *,
    allow: tuple[str, ...] = (),
    hooks: Mapping[str, object] | None = None,
    codex: str | None = None,
) -> Path:
    overlay = store.parents[2]
    (overlay / COMMON_CLAUDE / "permissions.json").write_text(
        json.dumps({"permissions": {"allow": list(allow), "deny": []}}), encoding="utf-8"
    )
    (overlay / COMMON_CLAUDE / "hooks.json").write_text(
        json.dumps({"hooks": dict(hooks or {})}), encoding="utf-8"
    )
    if codex is not None:
        (overlay / COMMON_CODEX / "common.rules").write_text(codex, encoding="utf-8")
    return overlay


def _attachable(
    tmp_path: Path,
    *,
    recorded: str | None = None,
    origin: str = "git@example.com:o/p.git",
    allow: tuple[str, ...] = (),
    hooks: Mapping[str, object] | None = None,
    codex: str | None = None,
) -> tuple[Path, Path, Path]:
    root, store = _project_and_store(tmp_path, recorded=recorded, origin=origin)
    _overlay_grants(store, allow=allow, hooks=hooks, codex=codex)
    return root, store, _machine(tmp_path, overlay=store.parents[2])


def _check_ignore(root: Path, relative: str) -> bool:
    done = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative],
        cwd=root,
        capture_output=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
    )
    return done.returncode == 0


def test_a_mismatched_remote_refuses_and_writes_nothing(tmp_path: Path) -> None:
    # §6.3: "on a mismatch it refuses unless --trust-remote is given interactively". The
    # assertion that matters is the second half: snapshot every file under the root before,
    # expect `Refusal`, and compare the snapshot after. Not one byte changed.
    root, store, machine = _attachable(tmp_path, recorded="git@example.com:o/real.git")
    before = snapshot(root)
    # The mutation guard for the assertion below, and the Global Constraint that asks for it:
    # `snapshot` is a walk, so `snapshot(root) == before` passes vacuously the day the walk
    # stops finding files — and this is a test standing behind a refusal.
    assert before
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=FakeRunner(),
            home=tmp_path / "home",
        )
    assert_snapshot_unchanged(root, before)


def test_an_unconfirmed_attach_that_would_widen_a_permission_refuses(tmp_path: Path) -> None:
    # DP3, and the finding that produced it. The Global Constraints say `attach` writes
    # `settings.local.json` "only after a printed diff and an explicit confirmation", and an
    # earlier revision implemented that sentence with nothing at all: the only mechanism was a
    # Markdown step telling a model to run `--check` first. A repository that says "setup
    # requires `keelline attach --store <path it names>`" gets a compliant agent to grant it
    # tool permissions, and no human sees the diff.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=False,
            trust_remote=False,
            runner=FakeRunner(),
            home=tmp_path / "home",
        )
    assert not (root / SETTINGS).exists()


def test_an_attach_that_widens_nothing_needs_no_confirmation(tmp_path: Path) -> None:
    # The gate is on the capability, not on the command. An overlay with no allow rules and no
    # hooks — the state of a freshly created one — must still attach without a flag, or the
    # flag becomes something people pass reflexively.
    root, store, machine = _attachable(tmp_path)
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    assert attached.binding_recorded
    assert not attached.settings_written
    assert (root / LEDGER).is_file()


def test_confirmed_merges_the_rules_and_records_each_entry_under_its_own_id(
    tmp_path: Path,
) -> None:
    # `owned_ids` is keyed by id, so one shared id for N entries yields one provenance row and
    # the same id under two events silently keeps the last. Assert `owned_ids(document)` has
    # one entry per merged hook.
    hooks = {
        "SessionStart": [{"hooks": [ENTRY, {"type": "command", "command": "echo two"}]}],
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo t"}]}],
    }
    root, store, machine = _attachable(tmp_path, allow=(RULE,), hooks=hooks)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    document = (root / SETTINGS).read_text(encoding="utf-8")
    claimed = owned_ids(document)
    assert len(claimed) == 3, claimed
    assert set(claimed.values()) == {"SessionStart", "PreToolUse"}
    assert json.loads(document)["permissions"]["allow"] == [RULE]


def test_an_entry_the_overlay_stopped_granting_is_taken_back_out(tmp_path: Path) -> None:
    # I3, walked end to end: the overlay grants a hook entry, `attach` installs it, the owner
    # deletes it from the overlay, `attach` runs again. The second run adds nothing — no allow
    # rule, no wanted entry — so it used to return the document untouched, leaving a marked
    # entry that still FIRES while the ledger (rebuilt from the overlay) forgot it. `doctor`
    # then reads an entry claiming the marker and named in no ledger, goes red, and tells the
    # owner to remove an entry Keelline installed: a false red with actively wrong advice.
    #
    # `apply_entries(document, {})` is the engine's removal path and is what now runs.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, hooks=hooks)
    home = tmp_path / "home"
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=FakeRunner(),
        home=home,
    )
    installed = owned_ids((root / SETTINGS).read_text(encoding="utf-8"))
    # Non-vacuous: the sequence is only about a second run if the first one installed something.
    assert installed
    assert set(ledger(root).entries) == set(installed)

    _overlay_grants(store)  # the owner takes the entry out of the overlay
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=FakeRunner(),
        home=home,
    )
    assert attached.settings_written
    assert owned_ids((root / SETTINGS).read_text(encoding="utf-8")) == {}
    assert ledger(root).entries == {}


def test_a_second_attach_that_changes_nothing_leaves_the_settings_file_alone(
    tmp_path: Path,
) -> None:
    # The guard for the clause above: `owned_ids` widened the early return, and a widening that
    # went too far would reformat a file the owner owns on every run and report itself as a
    # write. An overlay that grants nothing and a project that was never attached still touch
    # nothing.
    root, store, machine = _attachable(tmp_path)
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    assert not attached.settings_written
    assert not (root / SETTINGS).exists()


def test_a_group_mixing_a_marked_entry_with_a_foreign_one_is_split_not_replaced(
    tmp_path: Path,
) -> None:
    # Inherited from `scaffold.apply_entries` rather than re-implemented, and asserted here
    # because this is the lane whose mistake would delete a developer's own hook.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, hooks=hooks)
    (root / ".claude").mkdir()
    (root / SETTINGS).write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {"type": "command", "command": "mine.sh"},
                                {
                                    "type": "command",
                                    "command": "stale.sh  # keelline:overlay-SessionStart-1",
                                },
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    document = (root / SETTINGS).read_text(encoding="utf-8")
    commands = [
        entry["command"]
        for group in json.loads(document)["hooks"]["SessionStart"]
        for entry in group["hooks"]
    ]
    assert "mine.sh" in commands
    assert "stale.sh  # keelline:overlay-SessionStart-1" not in commands
    assert "echo hello  # keelline:overlay-SessionStart-1" in commands


def test_a_first_attach_records_the_remote_and_the_date(tmp_path: Path) -> None:
    # §6.2: projects/<name>/project.toml holds "bound remote URL(s), first-attach date".
    import datetime
    import tomllib

    root, store, machine = _attachable(tmp_path)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    record = tomllib.loads((store.parent / "project.toml").read_text(encoding="utf-8"))
    assert record["remote"] == "git@example.com:o/p.git"
    assert datetime.date.fromisoformat(str(record["first_attach"]))


def test_a_record_that_already_binds_this_repository_is_left_alone(tmp_path: Path) -> None:
    # The record is the owner's consent, and its date is when they gave it. Rewriting it on
    # every attach turns a fact into a timestamp of the last run — so a repository the overlay
    # already records correctly is not written at all.
    import tomllib

    root, store, machine = _attachable(tmp_path)
    runner = FakeRunner()
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    record = store.parent / "project.toml"
    first = tomllib.loads(record.read_text(encoding="utf-8"))["first_attach"]
    record.write_text(
        record.read_text(encoding="utf-8").replace(str(first), "2000-01-01"), encoding="utf-8"
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert tomllib.loads(record.read_text(encoding="utf-8"))["first_attach"] == "2000-01-01"


def test_the_merged_rules_are_recorded_where_they_can_be_removed_again(tmp_path: Path) -> None:
    # DP4: the ledger lives under .keelline/local/, because the committed manifest would
    # publish a digest of the owner's personal allow rules to collaborators.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, allow=(RULE,), hooks=hooks)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    recorded = ledger(root)
    assert recorded.allow == (RULE,)
    assert recorded.entries == {"overlay-SessionStart-1": "SessionStart"}
    assert (root / LEDGER).is_file()


def test_attach_writes_the_ignore_region_that_keeps_the_ledger_untracked(tmp_path: Path) -> None:
    # The repository has no `.keelline` line today and the lane that would ship one
    # (templates/project/) is out of scope, so an earlier revision's confidentiality argument
    # rested on a file that does not exist. Assert the region exists after attach, and assert
    # `git check-ignore -q .keelline/local/attach.json` succeeds — not that nothing is tracked,
    # which passes on a fixture that has committed nothing.
    root, store, machine = _attachable(tmp_path)
    assert not _check_ignore(root, LEDGER)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    body = extract((root / ".gitignore").read_text(encoding="utf-8"), "ignore", Style.HASH)
    assert body is not None and ".keelline/local/" in body
    assert _check_ignore(root, LEDGER)


def test_the_ignore_region_is_written_before_the_ledger_and_not_merely_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The two tests around this one assert the region *exists* afterwards, which is a different
    # question from the one `attach`'s own comment states: the ledger holds the owner's personal
    # allow rules and lives under a path the repository has no `.gitignore` line for, so a ledger
    # written first is a ledger `git add -A` publishes to every collaborator in the window before
    # the region lands. `mutations.toml`'s entry for it replaced the call with `pass`, so both
    # named tests reddened against absence and nothing anywhere reddened against order.
    #
    # The order of the writes themselves, recorded at `fsops.write_within` — the one primitive
    # every write in this module goes through — rather than inferred from the tree afterwards,
    # because the tree afterwards is identical either way.
    #
    # Mutation: `mutations.toml`'s "the ignore region is written after the ledger it untracks".
    root, store, machine = _attachable(tmp_path)
    written: list[str] = []
    real = fsops.write_within

    def record(base: Path, relative: str, text: str, *, encoding: str = "utf-8") -> None:
        if base == root:
            written.append(relative)
        real(base, relative, text, encoding=encoding)

    monkeypatch.setattr(fsops, "write_within", record)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    assert ".gitignore" in written and LEDGER in written, written
    assert written.index(".gitignore") < written.index(LEDGER), written


def test_attach_leaves_every_other_line_of_an_existing_gitignore_alone(tmp_path: Path) -> None:
    # The whole point of a managed region, and the reason this does not need C2's manifest:
    # everything outside the two markers comes back out as it went in.
    root, store, machine = _attachable(tmp_path)
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    assert "node_modules/\n" in (root / ".gitignore").read_text(encoding="utf-8")


def test_attach_refuses_when_the_ignore_region_cannot_be_written(tmp_path: Path) -> None:
    # The other half: if the ledger cannot be made untracked, writing it is a leak, and the
    # right answer is to refuse rather than to warn.
    root, store, machine = _attachable(tmp_path)
    (root / ".gitignore").mkdir()
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=False,
            trust_remote=False,
            runner=FakeRunner(),
            home=tmp_path / "home",
        )
    assert not (root / LEDGER).exists()


def _with_groups(root: Path, listed: str) -> None:
    text = (root / "keelline.toml").read_text(encoding="utf-8")
    (root / "keelline.toml").write_text(
        text.replace('groups = ["developer", "project-stable"]', f"groups = {listed}"),
        encoding="utf-8",
    )


def test_a_memory_group_that_leaves_the_projects_share_is_refused_not_created(
    tmp_path: Path,
) -> None:
    # §7.4 and the Global Constraints' D15: `memory.groups` is repository-authored and reaches
    # no guard of its own — `config/paths.py` says so in as many words, and names this lane as
    # the one that has to call the containment itself. The entry decides a directory created
    # inside the OVERLAY, which is the one tree `attach` trusts, so a `..` in it is refused
    # rather than created, and refused rather than crashing out as a raw `OSError`.
    #
    # **And refused before the first write**, which is the half this case was missing. The
    # containment was called from `_prepare_store`, which runs after the ignore region, the
    # `.codex/rules/` copies, the settings merge, the ledger *and* the overlay's binding record
    # — so a clone committing the entry below got five artifacts written and exit 2, and
    # `doctor._attached` then reported the repository attached and the binding **bound**,
    # because the record had been written too. The overlay is left out of the snapshot on
    # purpose: the binding record lives there, and asserting on the repository is what the
    # separate assertion below the snapshot is for.
    #
    # Mutation: `mutations.toml`'s "the memory.groups containment is asked at write time only".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    _with_groups(root, '["../../escape"]')
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal) as refusal:
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=True,
            runner=FakeRunner(),
            home=tmp_path / "home",
        )
    # Non-vacuous: this refusal and not one of the five `attach` can raise before it.
    assert "memory.groups" in str(refusal.value)
    # The entry itself is repository-authored, so it is not quoted back.
    assert "../../escape" not in str(refusal.value)
    assert not (store.parents[2].parent / "escape").exists()
    assert_snapshot_unchanged(root, before)
    # The one write that is not under the root, and the one that made `doctor` say `bound`.
    assert not (store.parent / PROJECT_RECORD).exists()


def test_the_memory_group_refusal_is_reached_on_a_run_that_would_have_written(
    tmp_path: Path,
) -> None:
    # The vacuity guard for the snapshot above, and the same one finding 1 and the ledger
    # refusal carry: a refusal that writes nothing proves nothing if the run had nothing to
    # write. The identical fixture with a group name that stays inside this project's share
    # attaches, and leaves behind every artifact the case above has to prevent.
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    _with_groups(root, '["developer", "project-stable"]')
    before = snapshot(root)
    assert before
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=True,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    after = snapshot(root)
    added = set(after) - set(before)
    assert attached.settings_written and attached.binding_recorded
    assert {LEDGER, SETTINGS, ".codex/rules/common.rules"} <= added
    assert before.get(".gitignore") != after.get(".gitignore")
    assert (store.parent / PROJECT_RECORD).is_file()
    assert (store / "project-stable").is_dir()


def test_a_second_attach_adds_nothing_twice(tmp_path: Path) -> None:
    # §6.3: "idempotent and reversible by detach". A permission list that grows by one copy of
    # every rule per attach is the shape this catches.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, allow=(RULE,), hooks=hooks)
    runner = FakeRunner()
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    document = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    assert document["permissions"]["allow"] == [RULE]
    assert len(document["hooks"]["SessionStart"]) == 1
    assert ledger(root).allow == (RULE,)


def test_a_second_attach_still_claims_what_the_first_one_added(tmp_path: Path) -> None:
    # The idempotence above is what makes this possible to get wrong: on the second run the
    # rule is already present, so the *diff* is empty — and a ledger written from the diff
    # alone would forget it, leaving `detach` nothing to remove.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    runner = FakeRunner()
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert ledger(root).allow == (RULE,)


def test_codex_rules_land_under_the_directory_codex_reads(tmp_path: Path) -> None:
    # §6.3: "places Codex rules under .codex/rules/". Kept separate from the Claude settings
    # merge because the two harnesses fail differently and a shared path would hide which.
    root, store, machine = _attachable(tmp_path, codex="# standing rule\n")
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    landed = root / ".codex" / "rules" / "common.rules"
    assert landed.read_text(encoding="utf-8") == "# standing rule\n"
    assert ".codex/rules/common.rules" in attached.rules_written
    assert ledger(root).rules == (".codex/rules/common.rules",)


def test_a_rule_the_overlay_never_granted_is_left_alone(tmp_path: Path) -> None:
    # §12: `doctor` lists every rule with provenance "so one no overlay granted is visible".
    # attach's own contribution to that is narrower and stricter: it does not touch one.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    (root / ".claude").mkdir()
    (root / SETTINGS).write_text(
        json.dumps({"permissions": {"allow": ["Bash(rm:*)"]}}), encoding="utf-8"
    )
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    allow = json.loads((root / SETTINGS).read_text(encoding="utf-8"))["permissions"]["allow"]
    assert allow == ["Bash(rm:*)", RULE]
    assert ledger(root).allow == (RULE,)


def test_the_secret_scan_is_installed_on_the_machine_that_never_ran_overlay_init(
    tmp_path: Path,
) -> None:
    # §6.3 asks `attach` to run `pre-commit install` in the overlay if it is missing, and Task
    # 6 only covers the first machine: a second one clones an overlay initialised elsewhere and
    # never runs `overlay init` again. Doing it twice is free; not doing it at all leaves the
    # commit-time secret scan unarmed on exactly the machine that thinks it is set up.
    root, store, machine = _attachable(tmp_path)
    _overlay_repository(store.parents[2])
    (store.parents[2] / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    runner = FakeRunner()
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert ["pre-commit", "install"] in runner.calls
    assert any("pre-commit" in note for note in attached.notes)


def test_trust_remote_rebinds_and_keeps_the_original_first_attach_date(tmp_path: Path) -> None:
    # The only path that rewrites an existing record, and the reason the date is read back
    # rather than re-stamped: `first_attach` is when the owner first consented, not when they
    # last ran the command.
    import tomllib

    root, store, machine = _attachable(tmp_path, recorded="git@example.com:o/real.git")
    (store.parent / "project.toml").write_text(
        'remote = "git@example.com:o/real.git"\nfirst_attach = "2020-02-02"\n', encoding="utf-8"
    )
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=True,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    assert attached.binding_recorded
    record = tomllib.loads((store.parent / "project.toml").read_text(encoding="utf-8"))
    assert record["remote"] == "git@example.com:o/p.git"
    assert record["first_attach"] == "2020-02-02"


def test_a_repository_with_no_origin_remote_has_nothing_to_record(tmp_path: Path) -> None:
    # An empty `remote` in the overlay's record would read as bound to nothing, and
    # `memory.store._bound` would then refuse every session with advice to run this command.
    #
    # **The snapshot is the half that was missing**, and it is the same snapshot
    # `test_a_mismatched_remote_refuses_and_writes_nothing` takes for the same reason. Asserting
    # only that `Refusal` is raised passed while the refusal lived in `_record_binding` — after
    # the ignore region, the `.codex/rules/` copies, the settings merge and the ledger. So a
    # checkout with no `origin` exited 2 having written four artifacts, and `doctor._attached`,
    # which keys on the ledger existing, then reported it attached. A refusal that leaves a
    # repository looking attached is not a refusal, and only a snapshot says so.
    #
    # Mutation: move the `if binding.remote is None` guard in `attach` back below
    # `_write_ignore_region`, and this reddens on the snapshot while `pytest.raises` stays green.
    root, store, machine = _attachable(tmp_path, codex="# a standing rule\n")
    subprocess.run(["git", "remote", "remove", "origin"], cwd=root, capture_output=True)
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=False,
            trust_remote=True,
            runner=FakeRunner(),
            home=tmp_path / "home",
        )
    assert_snapshot_unchanged(root, before)


def test_the_no_origin_refusal_is_reached_with_a_diff_that_would_have_written(
    tmp_path: Path,
) -> None:
    # The vacuity guard for the case above: a refusal that writes nothing proves nothing if the
    # run had nothing to write. The same overlay, with an allow rule, a hook entry and a Codex
    # rule file, attaches and writes all of them when `origin` is there — so the snapshot above
    # is measuring a run that would otherwise have left four artifacts behind.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(
        tmp_path, allow=(RULE,), hooks=hooks, codex="# a standing rule\n"
    )
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=True,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    assert attached.settings_written
    assert attached.rules_written == (".codex/rules/common.rules",)
    assert (root / LEDGER).is_file()
    assert (root / ".gitignore").is_file()


def test_a_settings_file_the_merge_cannot_read_is_refused_and_never_filtered(
    tmp_path: Path,
) -> None:
    # `scaffold.entries`' rule, one file over: what a filter drops here is somebody's own
    # setting, and nothing would say it went.
    root, store, machine = _attachable(tmp_path, allow=(RULE,))
    (root / ".claude").mkdir()
    (root / SETTINGS).write_text(json.dumps({"permissions": {"allow": "all"}}), encoding="utf-8")
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=FakeRunner(),
            home=tmp_path / "home",
        )


def test_an_overlay_hooks_file_with_an_unreadable_shape_is_refused(tmp_path: Path) -> None:
    # The same rule on the other side. An overlay entry this cannot key is one the owner put
    # there on purpose, and installing the rest of the file while dropping it silently is how
    # a hook goes missing with nothing to say so.
    root, store, machine = _attachable(tmp_path)
    (store.parents[2] / COMMON_CLAUDE / "hooks.json").write_text(
        json.dumps({"hooks": {"SessionStart": "not a list"}}), encoding="utf-8"
    )
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=FakeRunner(),
            home=tmp_path / "home",
        )


def test_a_ledger_that_is_not_json_is_a_failure_and_not_an_empty_one(tmp_path: Path) -> None:
    # An empty ledger reads as "attach added nothing", which makes `detach` a no-op on a
    # repository that has Keelline's rules in it — the quiet half of the failure this file is
    # the only witness to.
    root, store, machine = _attachable(tmp_path)
    attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    (root / LEDGER).write_text("{", encoding="utf-8")
    with pytest.raises(Failure):
        ledger(root)


def test_a_pre_commit_that_is_already_installed_is_not_run_again(tmp_path: Path) -> None:
    root, store, machine = _attachable(tmp_path)
    overlay = store.parents[2]
    hooks = _overlay_repository(overlay)
    (overlay / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    (hooks / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    runner = FakeRunner()
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert runner.calls == []
    assert attached.notes == ()


def test_a_hook_outside_dot_git_still_counts_as_installed(tmp_path: Path) -> None:
    # I2. The hook's directory is `git rev-parse --git-path hooks`, never `.git/hooks` and
    # never `core.hooksPath` read by hand — the rule `docs/cli.md` states for `setup
    # --git-hooks` and `guards.githooks.hooks_dir` implements. With `core.hooksPath` set, a
    # hardcoded path finds the scan missing on EVERY attach and shells out to `pre-commit
    # install` each time, on a machine where it is already armed.
    root, store, machine = _attachable(tmp_path)
    overlay = store.parents[2]
    hooks = _overlay_repository(overlay, hooks_path=tmp_path / "dotfiles" / "hooks")
    (overlay / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    (hooks / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    runner = FakeRunner()
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert runner.calls == []
    assert attached.notes == ()


def test_an_overlay_git_cannot_answer_about_is_a_note_and_never_a_traceback(
    tmp_path: Path,
) -> None:
    # `hooks_dir` refuses when `git` cannot name the directory — an overlay that is not a
    # repository at all is the cheapest such state. Every external binary is optional, so this
    # is a note; and `pre-commit install` is NOT fired blind at a directory nobody could place
    # a hook in.
    root, store, machine = _attachable(tmp_path)
    (store.parents[2] / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    runner = FakeRunner()
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert runner.calls == []
    assert any("hooks directory" in note for note in attached.notes)


def test_a_pre_commit_that_cannot_run_is_a_note_and_never_a_traceback(tmp_path: Path) -> None:
    # The Global Constraints make every external binary optional: a missing `pre-commit` is a
    # reported finding, and the push-time scan the template ships still runs.
    root, store, machine = _attachable(tmp_path)
    _overlay_repository(store.parents[2])
    (store.parents[2] / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    runner = FakeRunner(answer=Completed(127, "", "pre-commit could not be run"))
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=False,
        trust_remote=False,
        runner=runner,
        home=tmp_path / "home",
    )
    assert any("did not run" in note for note in attached.notes)


def _committed_ledger(root: Path, store: Path, **fields: object) -> None:
    """The ledger a clone committed, as a fresh checkout can genuinely hold one.

    `.gitignore` does not untrack a file a clone committed, and the `keelline:ignore` region
    `attach` writes does not either — so this path can be populated before `attach` has ever run
    here, which is the state both cases below are about.
    """
    document: dict[str, object] = {
        "format": 1,
        "store": str(store),
        "allow": [],
        "entries": {},
        "rules": [],
        "settings_keys": [],
    }
    document.update(fields)
    (root / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (root / LEDGER).write_text(json.dumps(document), encoding="utf-8")


def test_a_ledger_no_attach_could_have_written_is_refused_before_the_first_write(
    tmp_path: Path,
) -> None:
    # The same shape as `test_a_repository_with_no_origin_remote_has_nothing_to_record`, one
    # door over, and introduced by the commit that wrote that rule down. `ledger()` refuses a
    # ledger naming files or settings keys `attach` could not have written, and `_write_ledger`
    # used to be the thing that asked for it — from the fourth write of the run. So a clone
    # committing such a ledger got `attach` to write the `keelline:ignore` region, copy
    # `.codex/rules/*` and merge `.claude/settings.local.json`, and only then exit 2 — with the
    # committed ledger still on disk, which `doctor._attached` keys on. `attach --check` reports
    # clean beforehand, because it does not read the ledger at all.
    #
    # Nothing the repository gains here differs from a successful attach, so this is not a trust
    # boundary being crossed. What it is, is `docs/cli.md` asserting that every cause of exit 2
    # happens before the first write while one of them did not.
    #
    # Mutation: `mutations.toml`'s "the ledger is read after attach has already written".
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    _committed_ledger(root, store, rules=[".github/workflows/ci.yml"])
    before = snapshot(root)
    # `snapshot` is a walk, and an empty one satisfies the comparison below on its own.
    assert before
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=True,
            runner=FakeRunner(),
            home=tmp_path / "home",
        )
    assert_snapshot_unchanged(root, before)


def test_the_refused_ledger_is_reached_on_a_run_that_would_have_written_three_files(
    tmp_path: Path,
) -> None:
    # The vacuity guard for the case above, and the same one finding 1's snapshot has: a refusal
    # that writes nothing proves nothing if the run had nothing to write. The identical fixture,
    # with a ledger `attach` really could have written, attaches and leaves all three artifacts
    # the refusal above has to prevent.
    root, store, machine = _attachable(tmp_path, allow=(RULE,), codex="# a standing rule\n")
    _committed_ledger(root, store, rules=[".codex/rules/common.rules"])
    before = snapshot(root)
    assert before
    attached = attach(
        root,
        store=store,
        machine=machine,
        confirmed=True,
        trust_remote=True,
        runner=FakeRunner(),
        home=tmp_path / "home",
    )
    after = snapshot(root)
    assert attached.settings_written
    assert ".codex/rules/common.rules" in set(after) - set(before)
    assert SETTINGS in set(after) - set(before)
    assert before.get(".gitignore") != after.get(".gitignore")
    # And the union the ledger exists for survived the refusal being hoisted out of the writer:
    # `_write_ledger` is handed the ledger the caller read once, above every write.
    assert ledger(root).rules == (".codex/rules/common.rules",)


def test_an_overlay_store_the_walk_cannot_enter_is_refused_at_write_time(tmp_path: Path) -> None:
    # The floor under the containment hoisted above every write, and the proof it is not dead.
    # `config.paths.contained` answers about a *spelling* and about the symlinks it can see when
    # it looks; `fsops.mkdirs_within` asks the filesystem again at the moment of writing, through
    # the `O_NOFOLLOW` walk, which is the only thing that can catch a component that is not a
    # directory — or became a symlink in between. Here the overlay holds a regular file where
    # this project's memory directory belongs, which `contained` passes and the walk refuses.
    #
    # This is the one remaining way this refusal can arrive after a write, and it is a fact
    # about the overlay — the owner's own tree — rather than about a repository-authored entry.
    #
    # Mutation: `mutations.toml`'s "the write-time containment on the overlay's store directory
    # is swallowed".
    root, store, machine = _attachable(tmp_path)
    shutil.rmtree(store)
    store.write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(Refusal) as refusal:
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=True,
            runner=FakeRunner(),
            home=tmp_path / "home",
        )
    assert "memory.groups" in str(refusal.value)
