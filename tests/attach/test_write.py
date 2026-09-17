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

from keelline.attach.api import attach, ledger
from keelline.errors import Failure, Refusal
from keelline.overlay.api import COMMON_CLAUDE, COMMON_CODEX, Completed
from keelline.scaffold import Style, extract, owned_ids

# The fixture the binding tests already build, reused rather than copied: one spelling of the
# overlay layout keeps the two modules from drifting apart about what `--store` names.
from tests.attach.test_binding import _machine, _project_and_store

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


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every regular file under the root, by relative path — `.git` included deliberately."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
    before = _snapshot(root)
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=True,
            trust_remote=False,
            runner=FakeRunner(),
        )
    assert _snapshot(root) == before


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
        )
    assert not (root / SETTINGS).exists()


def test_an_attach_that_widens_nothing_needs_no_confirmation(tmp_path: Path) -> None:
    # The gate is on the capability, not on the command. An overlay with no allow rules and no
    # hooks — the state of a freshly created one — must still attach without a flag, or the
    # flag becomes something people pass reflexively.
    root, store, machine = _attachable(tmp_path)
    attached = attach(
        root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=FakeRunner()
    )
    assert attached.ignored and attached.binding_recorded
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
        root, store=store, machine=machine, confirmed=True, trust_remote=False, runner=FakeRunner()
    )
    document = (root / SETTINGS).read_text(encoding="utf-8")
    claimed = owned_ids(document)
    assert len(claimed) == 3, claimed
    assert set(claimed.values()) == {"SessionStart", "PreToolUse"}
    assert json.loads(document)["permissions"]["allow"] == [RULE]


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
        root, store=store, machine=machine, confirmed=True, trust_remote=False, runner=FakeRunner()
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
        root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=FakeRunner()
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
    attach(root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=runner)
    record = store.parent / "project.toml"
    first = tomllib.loads(record.read_text(encoding="utf-8"))["first_attach"]
    record.write_text(
        record.read_text(encoding="utf-8").replace(str(first), "2000-01-01"), encoding="utf-8"
    )
    attach(root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=runner)
    assert tomllib.loads(record.read_text(encoding="utf-8"))["first_attach"] == "2000-01-01"


def test_the_merged_rules_are_recorded_where_they_can_be_removed_again(tmp_path: Path) -> None:
    # DP4: the ledger lives under .keelline/local/, because the committed manifest would
    # publish a digest of the owner's personal allow rules to collaborators.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, allow=(RULE,), hooks=hooks)
    attach(
        root, store=store, machine=machine, confirmed=True, trust_remote=False, runner=FakeRunner()
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
        root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=FakeRunner()
    )
    body = extract((root / ".gitignore").read_text(encoding="utf-8"), "ignore", Style.HASH)
    assert body is not None and ".keelline/local/" in body
    assert _check_ignore(root, LEDGER)


def test_attach_leaves_every_other_line_of_an_existing_gitignore_alone(tmp_path: Path) -> None:
    # The whole point of a managed region, and the reason this does not need C2's manifest:
    # everything outside the two markers comes back out as it went in.
    root, store, machine = _attachable(tmp_path)
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    attach(
        root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=FakeRunner()
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
        )
    assert not (root / LEDGER).exists()


def test_a_second_attach_adds_nothing_twice(tmp_path: Path) -> None:
    # §6.3: "idempotent and reversible by detach". A permission list that grows by one copy of
    # every rule per attach is the shape this catches.
    hooks = {"SessionStart": [{"hooks": [ENTRY]}]}
    root, store, machine = _attachable(tmp_path, allow=(RULE,), hooks=hooks)
    runner = FakeRunner()
    attach(root, store=store, machine=machine, confirmed=True, trust_remote=False, runner=runner)
    attach(root, store=store, machine=machine, confirmed=True, trust_remote=False, runner=runner)
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
    attach(root, store=store, machine=machine, confirmed=True, trust_remote=False, runner=runner)
    attach(root, store=store, machine=machine, confirmed=True, trust_remote=False, runner=runner)
    assert ledger(root).allow == (RULE,)


def test_codex_rules_land_under_the_directory_codex_reads(tmp_path: Path) -> None:
    # §6.3: "places Codex rules under .codex/rules/". Kept separate from the Claude settings
    # merge because the two harnesses fail differently and a shared path would hide which.
    root, store, machine = _attachable(tmp_path, codex="# standing rule\n")
    attached = attach(
        root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=FakeRunner()
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
        root, store=store, machine=machine, confirmed=True, trust_remote=False, runner=FakeRunner()
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
    (store.parents[2] / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    runner = FakeRunner()
    attached = attach(
        root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=runner
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
        root, store=store, machine=machine, confirmed=False, trust_remote=True, runner=FakeRunner()
    )
    assert attached.binding_recorded
    record = tomllib.loads((store.parent / "project.toml").read_text(encoding="utf-8"))
    assert record["remote"] == "git@example.com:o/p.git"
    assert record["first_attach"] == "2020-02-02"


def test_a_repository_with_no_origin_remote_has_nothing_to_record(tmp_path: Path) -> None:
    # An empty `remote` in the overlay's record would read as bound to nothing, and
    # `memory.store._bound` would then refuse every session with advice to run this command.
    root, store, machine = _attachable(tmp_path)
    subprocess.run(["git", "remote", "remove", "origin"], cwd=root, capture_output=True)
    with pytest.raises(Refusal):
        attach(
            root,
            store=store,
            machine=machine,
            confirmed=False,
            trust_remote=True,
            runner=FakeRunner(),
        )


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
        )


def test_a_ledger_that_is_not_json_is_a_failure_and_not_an_empty_one(tmp_path: Path) -> None:
    # An empty ledger reads as "attach added nothing", which makes `detach` a no-op on a
    # repository that has Keelline's rules in it — the quiet half of the failure this file is
    # the only witness to.
    root, store, machine = _attachable(tmp_path)
    attach(
        root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=FakeRunner()
    )
    (root / LEDGER).write_text("{", encoding="utf-8")
    with pytest.raises(Failure):
        ledger(root)


def test_a_pre_commit_that_is_already_installed_is_not_run_again(tmp_path: Path) -> None:
    root, store, machine = _attachable(tmp_path)
    overlay = store.parents[2]
    (overlay / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    (overlay / ".git" / "hooks").mkdir(parents=True)
    (overlay / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    runner = FakeRunner()
    attached = attach(
        root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=runner
    )
    assert runner.calls == []
    assert attached.notes == ()


def test_a_pre_commit_that_cannot_run_is_a_note_and_never_a_traceback(tmp_path: Path) -> None:
    # The Global Constraints make every external binary optional: a missing `pre-commit` is a
    # reported finding, and the push-time scan the template ships still runs.
    root, store, machine = _attachable(tmp_path)
    (store.parents[2] / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")
    runner = FakeRunner(answer=Completed(127, "", "pre-commit could not be run"))
    attached = attach(
        root, store=store, machine=machine, confirmed=False, trust_remote=False, runner=runner
    )
    assert any("did not run" in note for note in attached.notes)
