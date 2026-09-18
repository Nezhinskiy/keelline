"""`setup(preset, ...)`: the walkthrough's steps 3 and 4 (§4) — machine setup, once.

Five things, each reported and each independently skippable, in this order: write the machine
file (the personal defaults the preset names, for whichever of them nothing has recorded yet);
merge the preset's deny rules and the personal values into the machine-scope settings file;
register each preset plugin's marketplace and install from it, per configured harness; report
whether `keelline` itself resolves on `PATH`; and, only when the caller named an answer, create
or record the private overlay.

**A preset default never overwrites a value already recorded.** The first draft of this module
rebuilt `[personal]` from the preset's own defaults on every run, which meant a second
`setup --preset recommended` reset `reply_language` back to `""` even after the owner had set it
by hand — exactly the value `skills/setup/SKILL.md` calls "the user's to set" and
`setup.machine`'s own docstring promises survives a rewrite that "only set one of them" (Fix
round 1, item 1). `_new_personal_values` computes only the keys the machine file does not
already carry, and that is what both `write_machine` and the settings file's `pluginConfigs`
receive — an empty dict on every run after the first, once every key has a recorded value.

**Marketplaces are registered before anything is installed from them, and per-plugin sources
are never guessed.** The first draft attempted `claude plugin install superpowers@obra` on a
fresh machine and always failed there — `obra` and `upstash` are GitHub accounts, not
marketplace names, and every measured successful install in this tree's own spike record
(`docs/plans/2026-09-05-agent-harness-p0-spikes.md`) is preceded by a `marketplace add`
(Fix round 1, item 2). Checked before writing this fix (`gh api repos/...`, `claude plugin
marketplace list` on the machine this was written on): `superpowers` and `context7` both ship
in Anthropic's own official marketplace, `anthropics/claude-plugins-official`, which a Claude
Code install already carries — the `marketplace add` this module still issues is idempotent
defence in depth, not a first registration, and its own real output confirms that
(`✔ Marketplace 'claude-plugins-official' already on disk`). No non-interactive, non-guessed
source could be established for Codex, so nothing is attempted there for these two plugins; the
recommended preset's own `[plugins.claude]` table and the README carry the reasoning and the
recommendation respectively.

**Two harnesses, two verbs, and no unmeasured flags.** Claude Code installs a plugin with
`claude plugin install <name>@<marketplace>`, bare — the spike record's own transcript reports
`(scope: user)` as the *default* a bare install already gets, not something a flag adds, and
`-y` appears in that record only on `plugin uninstall`, never `install` (Fix round 1, item 3).
Codex adds one with `codex plugin add <name>@<marketplace>` when a marketplace is declared for
it — measured, not assumed, from this tree's own spike Task 1 and Task 2. A harness or a plugin
with no declared marketplace gets a note, never a guessed argv.

**`pluginConfigs` and not a flat top-level key.** Claude Code's own settings reference files a
plugin's non-sensitive `userConfig` answers under `pluginConfigs[<plugin-id>].options`, keyed by
`<plugin-name>@<marketplace-name>` and not by the plugin name alone — confirmed against
`code.claude.com/docs/en/settings-reference` before this was written, because a flatter shape
would round-trip through nothing Claude Code itself reads. `PLUGIN_ID` matches this repository's
own shipped manifest and marketplace names (`tests/test_manifests.py`), which is the pair this
plugin is actually installed under everywhere the preset's own `setup` runs.

**The overlay root is validated before anything is written, and the create branch is gated on
`--yes`.** The coordinator's ruling on the named risk this wave's first report raised: `--yes`
on `--overlay <path>` would be theatre in a harness where the command line is written by a
model, so it is not added there. What bounds the exposure instead is `_requested_overlay`, and
it runs **above the first write** — above the machine file, the settings merge and the plugin
installs, and for `create:` above `gh repo create` itself. Two controls:

* **it must be an overlay**, which is `overlay.api.require_overlay` and not a pair of `is_file`
  calls. The old probe was the two manifests *existing*, which the Keelline checkout satisfies
  and any Claude Code plugin repository satisfies; the probe now reads them and requires them to
  name the tree `keelline-overlay[-<owner>]` and `keelline-overlay-marketplace[-<owner>]`, the
  names `overlay init` writes and a harness installs an overlay by. `identity`'s own docstring
  is honest that a repository can still *claim* those names: it stops the accidents, and it
  stops this half from standing for nothing.
* **it must lie outside the repository the agent works in**, which now means outside *every*
  checkout of it. The old check refused `candidate == project` or `project in candidate.parents`
  and nothing else, so a parent directory and a sibling worktree both passed — and this
  project's own `worktree-by-default` preset rule makes `--root` a worktree, which is exactly
  the shape that passed. It now also refuses a candidate that *holds* the project root, and a
  candidate whose `git rev-parse --git-common-dir` is the project root's: what a repository
  ships reaches its own checkouts and nowhere else, so refusing every checkout of it removes the
  tree a clone can stage. It is not a claim that the same bytes cannot be somewhere else on the
  machine — a separate clone of the same remote passes — only that the owner put them there.
  When `git` cannot answer for the project root — it is not a repository, or `git` is not
  installed — only the path arms stand, and that is stated rather than assumed.

For `create:`, the destination is `home/<name>` and is knowable from the arguments
(`overlay.api.target_root`), so it is checked before the call rather than after it: the first
draft ran `gh repo create`, cloned, renamed both manifests and installed the secret scan, and
*then* refused — leaving a private repository on somebody's GitHub account that nothing in the
report mentioned. `--yes` gets the one real control the ruling does give it: `setup` refuses
`--overlay create:<owner>/<name>` without it, because §6.1 asks for "explicit confirmation"
before `gh repo create` runs, and creating a repository on GitHub is the one irreversible,
outward-facing act this command performs.

**A symlinked settings file is a refusal with a remedy that works, not an internal error.**
`home` is the machine owner's own directory and a home managed by stow, chezmoi or a synced
directory is the
most common non-default layout there is, but the settings file still goes through the
`O_NOFOLLOW` walk — so the containment rule's two stages both apply here: `config.paths
.contained` gives the user-facing refusal above the first write, and `fsops.write_within` is the
floor under it for a component that becomes a symlink afterwards. Before, only the second stage
existed, and it surfaced as `keelline: internal error: UnsafePath` after the machine file had
already been written. What the refusal prints is held to the same standard as the refusal
itself: `_home_that_leads_there` offers a `--home` only when that `--home` really writes the file
the link leads to, and says plainly that no such value exists when none does — a remedy that
exits 0 into a file no reader reads is the defect one door over.
"""

from __future__ import annotations

import datetime
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from keelline import __version__, fsops
from keelline.config.paths import PathEscape, contained
from keelline.errors import Failure, Refusal
from keelline.fsops import UnsafePath
from keelline.gitenv import git_run
from keelline.overlay.api import (
    Runner,
    create,
    init_instance,
    overlay_fault,
    require_overlay,
    target_root,
)
from keelline.presets import load_preset
from keelline.setup.machine import USER_SETTINGS, read_machine, write_machine

# `<plugin-name>@<marketplace-name>`, matching `.claude-plugin/plugin.json`'s `name` and
# `.claude-plugin/marketplace.json`'s `name` (`tests/test_manifests.py` holds both). Claude
# Code keys `pluginConfigs` by this pair, not by the plugin name alone.
PLUGIN_ID = "keelline@keelline-marketplace"
# The release tag scheme (`vX.Y.Z`, §5.9); `uv tool install` has no `--from`, so the positional
# git URL form is the one D2 permits (`git+https://…@<tag>`).
INSTALL_COMMAND = "uv tool install git+https://github.com/Nezhinskiy/keelline@v{version}"
# One verb pair per harness, fixed here rather than in the preset: which CLI verb installs a
# plugin is a property of the harness, never of any one plugin, and the two differ (measured,
# Fix round 1 item 3's docstring paragraph above).
_MARKETPLACE_ADD = {
    "claude": lambda source: ["claude", "plugin", "marketplace", "add", source],
    "codex": lambda source: ["codex", "plugin", "marketplace", "add", source],
}
_PLUGIN_INSTALL = {
    "claude": lambda full: ["claude", "plugin", "install", full],
    "codex": lambda full: ["codex", "plugin", "add", full],
}
# What `--overlay <path>` and `--overlay create:` are each about to do, for the refusal the
# overlay probe raises. One sentence each, so the two commands that ask "is this an overlay"
# differ in what they were doing and not in what the answer means.
_RECORDING = (
    "--overlay must name a real overlay's root — the tree `keelline overlay create` renders "
    "and `keelline overlay init` names after you — because this path becomes the machine's "
    "trust anchor: every `keelline attach` on this machine reads rules and notes out of it"
)
_CREATED = (
    "the repository was created and cloned, and nothing was recorded in the machine "
    "configuration; look at what arrived, then record it with `keelline setup --overlay <path>`"
)
# Both halves of the containment rule for the settings file, said once. The refusal above the
# first write names the link and the way out; the walk at write time is the floor under it.
_SYMLINKED_SETTINGS = (
    f"keelline writes {USER_SETTINGS} through a walk that never follows a symlink, so it will "
    f"not write through this one"
)


@dataclass(frozen=True)
class SetupReport:
    """What one `setup` run did. Every field here is this run's own computation, printable."""

    machine_written: bool
    plugins_installed: tuple[str, ...]
    deny_written: bool
    cli_on_path: bool
    overlay: Path | None
    notes: tuple[str, ...]


def _personal_defaults(preset: dict[str, Any]) -> dict[str, Any]:
    return dict(preset.get("defaults", {}).get("personal", {}))


def _existing_personal(machine: Path) -> dict[str, Any]:
    if not machine.is_file():
        return {}
    raw = read_machine(machine).get("personal")
    return dict(raw) if isinstance(raw, dict) else {}


def _new_personal_values(preset: dict[str, Any], machine: Path) -> dict[str, Any]:
    """The preset's personal defaults, minus every key the machine file already carries.

    A key present in the file — set by an earlier `setup`, or by the owner's own hand — is the
    owner's, and a preset default may not win over it on a later run. An absent key gets the
    preset's default, which is what makes a *first* run write all three (Fix round 1, item 1).
    """
    existing = _existing_personal(machine)
    return {k: v for k, v in _personal_defaults(preset).items() if k not in existing}


def _agents(preset: dict[str, Any]) -> tuple[str, ...]:
    agents = preset.get("defaults", {}).get("keelline", {}).get("agents", [])
    return tuple(agent for agent in agents if isinstance(agent, str))


def _marketplace(preset: dict[str, Any], agent: str) -> tuple[str, str] | None:
    """`(source, marketplace name)` for `agent`, or `None` when the preset declares none.

    `None` is not a fault: it is "nothing here is vendored for this harness on a guess" (§5.6),
    and the caller reports it as a note rather than attempting an argv nobody measured.
    """
    table = preset.get("plugins", {}).get(agent)
    if not isinstance(table, dict):
        return None
    source, marketplace = table.get("source"), table.get("marketplace")
    if not isinstance(source, str) or not isinstance(marketplace, str):
        return None
    return source, marketplace


def _install_plugins(
    preset: dict[str, Any], agents: Sequence[str], *, home: Path, runner: Runner
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    selectors = [s for s in preset.get("plugins", {}).get("install", []) if isinstance(s, str)]
    installed: list[str] = []
    notes: list[str] = []
    for agent in agents:
        market = _marketplace(preset, agent)
        if market is None:
            if selectors:
                notes.append(
                    f"{agent}: no verified marketplace for {', '.join(selectors)}; "
                    f"install manually if this harness supports it (see README)"
                )
            continue
        source, marketplace = market
        add_argv_of, install_argv_of = _MARKETPLACE_ADD.get(agent), _PLUGIN_INSTALL.get(agent)
        if add_argv_of is None or install_argv_of is None:
            notes.append(f"{agent}: no known plugin command for this harness")
            continue
        # Idempotent by construction: an already-registered source is a note from `claude`/
        # `codex` themselves ("already on disk"), read here through the same non-zero-is-a-note
        # path as everything else — a missing binary is `Completed(127, ...)` from `Runner`
        # itself (its own docstring: "a missing binary is a finding, never a traceback").
        added = runner.run(add_argv_of(source), home)
        if added.code != 0:
            detail = added.stderr.strip() or added.stdout.strip() or f"exit {added.code}"
            notes.append(f"{agent}: could not register marketplace {source} ({detail})")
            continue
        for selector in selectors:
            argv = install_argv_of(f"{selector}@{marketplace}")
            done = runner.run(argv, home)
            if done.code == 0:
                if selector not in installed:
                    installed.append(selector)
            else:
                detail = done.stderr.strip() or done.stdout.strip() or f"exit {done.code}"
                notes.append(f"{agent}: `{' '.join(argv)}` did not succeed ({detail})")
    return tuple(installed), tuple(notes)


def _read_document(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, ""
    except OSError as exc:
        raise Failure(f"{path} cannot be read: {exc}") from exc
    if not text.strip():
        return {}, text
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Failure(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise Failure(f"{path} is not a JSON object")
    return raw, text


def _write_user_settings(
    home: Path, deny_rules: Sequence[str], personal: Mapping[str, Any]
) -> bool:
    """Merge the preset's deny rules and the personal values into `<home>/<USER_SETTINGS>`.

    Merge, never replace: the owner's own file predates Keelline on most machines, and nothing
    this run did not add may be recorded as if it had. Deny only — this never reads or writes
    `permissions.allow` — and `pluginConfigs` gets the same treatment, key by key inside its own
    `options`, so a value this run did not set survives a second one same as `write_machine`'s.
    """
    path = home / USER_SETTINGS
    document, text = _read_document(path)

    permissions = document.get("permissions")
    permissions = dict(permissions) if isinstance(permissions, dict) else {}
    raw_deny = permissions.get("deny")
    existing_deny = (
        [r for r in raw_deny if isinstance(r, str)] if isinstance(raw_deny, list) else []
    )
    permissions["deny"] = existing_deny + [r for r in deny_rules if r not in existing_deny]
    document["permissions"] = permissions

    plugin_configs = document.get("pluginConfigs")
    plugin_configs = dict(plugin_configs) if isinstance(plugin_configs, dict) else {}
    entry = plugin_configs.get(PLUGIN_ID)
    entry = dict(entry) if isinstance(entry, dict) else {}
    options = entry.get("options")
    options = dict(options) if isinstance(options, dict) else {}
    options.update(personal)
    entry["options"] = options
    plugin_configs[PLUGIN_ID] = entry
    document["pluginConfigs"] = plugin_configs

    new_text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if new_text == text:
        return False
    try:
        fsops.write_within(home, USER_SETTINGS, new_text)
    except UnsafePath as exc:
        # The floor under `_check_settings_path`, and not dead: a component that became a
        # symlink, or stopped being a directory, between that check and this write can only be
        # refused here. `UnsafePath` is an `OSError`, and reaching `cli.run`'s final handler is
        # what made the ordinary symlinked `~/.claude` an `internal error`.
        raise Refusal(
            f"{home / USER_SETTINGS} cannot be written: {exc}; {_SYMLINKED_SETTINGS}"
        ) from exc
    return True


def _settings_symlink(home: Path) -> Path | None:
    """The first symlink between `home` and the settings file, or `None`."""
    target = home / USER_SETTINGS
    for ancestor in [target, *target.parents]:
        if ancestor == home:
            return None
        if ancestor.is_symlink():
            return ancestor
    return None


def _home_that_leads_there(home: Path, link: Path) -> Path | None:
    """The `--home` whose own walk writes the file this link leads to, or `None` for a layout no
    `--home` can express.

    One computation for both shapes of the same accident, because the first draft had one arm
    written for the directory shape and it misfired on the other. `stow` folds a package as far
    as it can: with `~/.claude` already created by Claude Code it links the *file*, so the link
    is `~/.claude/settings.json -> <dotfiles>/claude/settings.json`. The old remedy compared the
    link's basename to its target's, which is trivially true for a per-file link, and printed
    `--home <dotfiles>/claude` — under which this command writes
    `<dotfiles>/claude/.claude/settings.json`, exits 0, and leaves the file the link leads to
    untouched and every reader reading nothing. That is finding 14's shape arriving through the
    remedy instead of through the default.

    What `--home H` actually writes is `H/<USER_SETTINGS>` and nothing else, so a remedy exists
    exactly when what the link leads to *is* a `<USER_SETTINGS>` inside some directory — and
    that directory is the answer. Whatever of `USER_SETTINGS` lies below the link still follows
    it, which is what puts the directory and the file shapes into one expression.
    """
    wanted = Path(USER_SETTINGS).parts
    leads_to = link.resolve() / (home / USER_SETTINGS).relative_to(link)
    if leads_to.parts[-len(wanted) :] != wanted:
        return None
    return leads_to.parents[len(wanted) - 1]


def _check_settings_path(home: Path) -> None:
    """Refuse a `~/.claude` this command cannot write through — above the first write.

    `home` is the machine owner's own directory rather than an untrusted root, but the write
    goes through the `O_NOFOLLOW` walk all the same, and the walk had no user-facing half: a
    home managed by stow, chezmoi or a synced directory raised `UnsafePath` out of
    `fsops.write_within`, which `cli.run` rendered as `keelline: internal error: UnsafePath:
    '.claude/settings.json': '.claude' is a symlink or not a directory`, exit 2 — after the
    machine file had been written. `config.paths.contained` is the missing half, and this
    translates its verdict into a refusal that names the link and the way out.
    """
    try:
        contained(home, USER_SETTINGS)
    except PathEscape as exc:
        link = _settings_symlink(home)
        if link is None:
            raise
        real = link.resolve()
        instead = _home_that_leads_there(home, link)
        kind = "file" if link == home / USER_SETTINGS else "directory"
        if instead is not None:
            remedy = (
                f"run `keelline setup --home {instead}`, which writes the file this link leads "
                f"to, or replace the link with a real {kind}"
            )
        else:
            # An honest "this cannot be expressed" beats a command that writes somewhere else
            # and exits 0. The two ways out are named because both are ordinary dotfiles work:
            # `stow` can package the directory as `.claude`, and `stow --adopt` (and its
            # equivalents) take a real file back afterwards.
            remedy = (
                f"no --home can name it: this command writes <home>/{USER_SETTINGS} and nothing "
                f"else, and {real} is not a {USER_SETTINGS} inside any directory. Either point "
                f"the link at a path ending in {USER_SETTINGS}, or take the link away, let this "
                f"command write a real {kind}, and have your dotfiles manager adopt it"
            )
        raise Refusal(
            f"{link} is a symlink to {real}; {_SYMLINKED_SETTINGS}. A dotfiles manager or a "
            f"synced home is the usual reason — {remedy}"
        ) from exc


def _repository_of(path: Path) -> Path | None:
    """The git common directory `path` sits in, or `None` when `git` cannot say it is in one.

    Asked from the nearest directory that exists, because the create branch asks this about a
    destination that has not been created yet. `gitenv.git_run` scrubs `GIT_DIR` and
    `GIT_WORK_TREE`, so an inherited one cannot make two unrelated trees answer alike.
    """
    start = path if path.is_dir() else path.parent
    if not start.is_dir():
        return None
    code, out = git_run(start, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if code != 0 or not out.strip():
        return None
    return Path(out.strip()).resolve()


def _outside_the_project(candidate: Path, *, project_root: Path) -> None:
    """Refuse an overlay root that sits where the repository an agent works in could reach it.

    Three path arms and one `git` arm. The path arms are equality, nesting either way round —
    a candidate *under* the project, and a candidate that *holds* it, which is the shape
    `git worktree add .worktrees/x` produces and which the first draft accepted. The `git` arm
    is the sibling case the paths cannot see: `keelline.worktrees/wave-1` is not under
    `keelline/`, so a clone committing its own manifests at its own root passed both path arms
    whenever `--root` was one of its worktrees — and this project's own preset rule makes
    `--root` a worktree by default.

    **What it does not cover, stated rather than implied.** When `git` cannot answer for the
    project root — `--root` is not a repository, or `git` is not installed — the `git` arm is
    silent and only the paths stand. And what the whole check bounds is a repository *shipping* a
    tree: committed contents reach that repository's own checkouts and nowhere else, so refusing
    all of them removes the case a clone can stage. It is not a claim that no other directory on
    the machine can hold the same bytes — a separate `git clone` of the same remote has its own
    common directory and passes — only that the owner, and not the clone, put it there.
    """
    resolved_candidate = candidate.resolve()
    resolved_project = project_root.resolve()
    if (
        resolved_candidate == resolved_project
        or resolved_project in resolved_candidate.parents
        or resolved_candidate in resolved_project.parents
    ):
        raise Refusal(
            f"{candidate} is inside {project_root}, holds it, or is it — and {project_root} is "
            f"the project this command was run from. The overlay root is the machine's trust "
            f"anchor and must live outside any repository an agent works in: a repository could "
            f"otherwise ship its own tree and have this command record it"
        )
    project_repository = _repository_of(resolved_project)
    if project_repository is not None and _repository_of(resolved_candidate) == project_repository:
        raise Refusal(
            f"{candidate} is a checkout of the same repository as {project_root}, the project "
            f"this command was run from. The overlay root is the machine's trust anchor and "
            f"must live outside every checkout of a repository an agent works in — a worktree "
            f"is not a different repository, and a clone ships its own tree into all of them"
        )


@dataclass(frozen=True)
class _Overlay:
    """What `--overlay` asked for, once everything knowable before the first write is known.

    `create` is `(owner, name)` when this run has to create the repository, and `None` when the
    root already exists and is only being recorded. `root` is where the overlay is or will be:
    for the create branch it is `overlay.api.target_root`'s answer, computed from the arguments
    alone so the destination can be refused before `gh repo create` runs.
    """

    root: Path
    create: tuple[str, str] | None


def _requested_overlay(
    overlay: str | None, *, home: Path, project_root: Path, yes: bool
) -> _Overlay | None:
    """Every refusal `--overlay` can raise that does not need a tree to exist first.

    Called above the first write. The first draft called the equivalent of this from the bottom
    of `setup`, so `--overlay /typo` had already written the machine file, merged the settings
    file and installed two plugins before it refused, and `--overlay create:` had already
    created a private repository on GitHub.

    `home`, never `Path.cwd()`, is what a *created* overlay is created in: this is a machine
    command, run from wherever the owner happened to be sitting, and a created overlay must not
    depend on that. Measured while that was written: `root=Path.cwd()` created a real
    `keelline-private/` inside this very checkout the first time a test exercised the branch.
    """
    if overlay is None:
        # Nothing was asked for, so nothing is touched. §6.1's gate is that `--overlay` is the
        # only way to reach the overlay at all, and `--yes` does not imply one: a default here
        # would turn an omitted flag into a repository created on somebody's account.
        return None
    if overlay.startswith("create:"):
        if not yes:
            raise Refusal(
                "creating a private overlay runs `gh repo create ... --private --template ...` "
                "on GitHub, which §6.1 permits only after explicit confirmation; pass --yes to "
                "confirm it, or use --overlay <path> to record one that already exists"
            )
        spec = overlay[len("create:") :]
        owner, sep, name = spec.partition("/")
        if not sep or not owner or not name:
            raise Refusal(
                f"--overlay create:<owner>/<name> needs both a GitHub owner and a repository "
                f"name; got {overlay!r}"
            )
        # Refuses a name that is not one path segment, and answers where the tree would land —
        # both without creating anything, which is the whole point of asking here.
        destination, account = target_root(home, owner, name)
        _outside_the_project(destination, project_root=project_root)
        return _Overlay(root=destination, create=(account, name))
    candidate = Path(overlay).expanduser().resolve()
    require_overlay(candidate, because=_RECORDING)
    _outside_the_project(candidate, project_root=project_root)
    return _Overlay(root=candidate, create=None)


def _apply_overlay(planned: _Overlay, *, project_root: Path, runner: Runner) -> tuple[Path, str]:
    """Create the overlay if this run has to, record what there is, and say what happened.

    Everything here that can refuse is a **floor** under `_requested_overlay` rather than a
    second copy of it, in the sense the `attach` lane settled the same shape: the checks above
    the first write are what a person acts on, and these are what catches a tree that changed in
    between — or, for the create branch, one that did not exist to be checked at all. What this
    function returns is written into the machine file, and every later `attach` on this machine
    derives `permitted_roots` from that record, so the last thing to touch the tree before it
    becomes the trust anchor asks again.

    The created branch's refusal says the repository exists. It has to: the owner now has a
    private repository on GitHub that this run made, and the report is discarded on a refusal,
    so nothing else would ever tell them.
    """
    if planned.create is None:
        require_overlay(planned.root, because=_RECORDING)
        _outside_the_project(planned.root, project_root=project_root)
        return planned.root, f"recorded the existing overlay at {planned.root}"
    owner, name = planned.create
    created = create(owner, name, source="template", root=planned.root.parent, runner=runner)
    init_instance(created.root, owner, runner=runner)
    _outside_the_project(created.root, project_root=project_root)
    fault = overlay_fault(created.root)
    if fault is not None:
        raise Refusal(
            f"{fault}. {owner}/{name} was created and cloned to {created.root}, but {_CREATED}"
        )
    return created.root, f"created the overlay at {created.root}"


def setup(
    preset: str,
    *,
    home: Path,
    machine: Path,
    runner: Runner,
    yes: bool,
    overlay: str | None,
    project_root: Path,
) -> SetupReport:
    """Configure this machine from `preset`.

    `project_root` is the repository this invocation was run from (the CLI's `--root`, default
    `.`), and it exists for exactly one reason: `_outside_the_project` refuses an `--overlay`
    that any checkout of it could reach. `yes` takes the detected defaults for everything except
    creating an overlay, which needs it explicitly (see the module docstring).

    **Everything structural is asked before the first write**, and the order below is
    load-bearing rather than tidy: `--overlay` is parsed, probed and contained, and the settings
    path is checked, while nothing is on disk and no repository exists on anyone's GitHub
    account. What is left after that is the work, and the one refusal that follows a write is
    the post-condition on a tree this run created.
    """
    planned_overlay = _requested_overlay(overlay, home=home, project_root=project_root, yes=yes)
    _check_settings_path(home)

    # `home` is the root every write in this function lands under — the settings file through
    # `fsops.write_within` below, and a created overlay through `overlay.create` further down —
    # and it is not one this process was handed already existing, the way a project root or the
    # overlay itself is. Created directly for the same reason `setup.machine`'s module
    # docstring gives for `fsops.write_atomically` on the machine file: there is nothing for a
    # contained walk to be relative to until this directory exists.
    home.mkdir(parents=True, exist_ok=True)
    data = load_preset(preset)
    personal = _new_personal_values(data, machine)
    machine_table = {"version": __version__, "installed": datetime.date.today().isoformat()}
    write_machine(machine, personal=personal, overlay_root=None, machine=machine_table)

    deny_rules = [r for r in data.get("deny", {}).get("global", []) if isinstance(r, str)]
    # **The `pluginConfigs` mirror is recomputed from the machine file, not from this run's own
    # new keys.** `personal` above is empty on every run after the first, so the mirror was
    # write-once: an owner who edited `reply_language` in the machine file — the documented way,
    # `README.md`'s own "Written by: you, or `keelline setup`" — kept `""` in
    # `~/.claude/settings.json` for ever. The other answer the review offered was to stop
    # writing the mirror at all; it is rejected because `pluginConfigs` is where Claude Code
    # itself reads a plugin's `userConfig` answers, and this plugin's own manifest declares
    # them, so dropping it would leave the harness reading nothing. The cost of this direction
    # is stated where a reader will meet it: a value set in Claude Code's plugin-config UI is
    # overwritten by the machine file on the next `setup`, because one file has to win and the
    # machine file is the one every Keelline reader reads.
    deny_written = _write_user_settings(home, deny_rules, _existing_personal(machine))

    installed, install_notes = _install_plugins(data, _agents(data), home=home, runner=runner)
    notes = list(install_notes)

    cli_on_path = shutil.which("keelline") is not None
    if not cli_on_path:
        notes.append(
            f"`keelline` is not on PATH; install it with "
            f"`{INSTALL_COMMAND.format(version=__version__)}`"
        )

    overlay_root: Path | None = None
    if planned_overlay is not None:
        overlay_root, note = _apply_overlay(
            planned_overlay, project_root=project_root, runner=runner
        )
        notes.append(note)
        write_machine(machine, personal={}, overlay_root=overlay_root, machine={})

    return SetupReport(
        machine_written=True,
        plugins_installed=installed,
        deny_written=deny_written,
        cli_on_path=cli_on_path,
        overlay=overlay_root,
        notes=tuple(notes),
    )
