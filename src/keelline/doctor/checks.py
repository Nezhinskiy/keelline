"""The fifteen checks an installation is judged by (§8.4), and the context they share.

**A `Check` is not a `Finding`.** `findings.Finding` carries a rule, a path and a line, and its
docstring says the label is "what this lane computed" while the detail "may quote the
repository" and is for `--json`. A doctor row needs a fourth thing neither of those is — a
**remedy**, the command a reader is supposed to run next — and it has no path or line to carry.
Widening `Finding` would reach into three areas that depend on its current shape, so this area
defines its own record and reuses `findings.listed` for the summary line alone.

**What may be printed, and what may not.** Counts, labels, statuses and Keelline's own
vocabulary are computed here and print freely. A repository-authored string does not: not
`[keelline] version`, not `[ci] ref`, not a note's filename, not a hook command, not the reason
`memory.store` gives for an unresolvable store. §5.3 says it of the diagnostics log in as many
words — reasons, never payloads — and this module holds every other row to the same line.

**One exception, argued rather than assumed: a claimed marker id.** §12's row asks for exactly
this — "a hook entry adds the Keelline marker to a hostile command → doctor lists every entry
with provenance" — and a provenance list that cannot name the entry it is about is not one.
What is printed is the *id*, never the command: `scaffold.entries._MARKER` holds an id to
`[A-Za-z0-9][A-Za-z0-9._-]*`, so it carries no whitespace, no newline, no quote and no
delimiter, and it is truncated to `MARKER_ID_CHARS` here so that length cannot substitute for
content. That is a bounded, alphanumeric token in a field a reader is being asked to look at,
which is the narrowest shape this finding can take and still be the finding.

**`keelline.hooks.sink` is imported directly, and the Global Constraints' "import an area
through its published surface" is departed from here rather than satisfied.** `hooks/api.py` is
the handler protocol, imported at module scope by every area's `hooks.py`, and `sink.py` imports
*it* — so re-exporting the sink's names from `api.py` is an import cycle, not a tidying. The
plan's own `Consumes:` block names `keelline.hooks.sink`, and this is the note that says it was
a decision.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import keelline
from keelline.attach.api import LEDGER, MISMATCH, ledger, read_binding
from keelline.config.loader import CONFIG_FILE, load
from keelline.config.schema import Config
from keelline.errors import Failure, Refusal
from keelline.findings import listed
from keelline.hooks.sink import DIAGNOSTICS, DIRECTORY, MARKERS
from keelline.memory.api import (
    PROJECTS,
    SLOTS,
    GitUnavailable,
    Store,
    fit,
    harness_memory_path,
    overlay_root,
    render,
    resolve,
)
from keelline.overlay.api import Runner
from keelline.scaffold import owned_ids
from keelline.setup.api import USER_SETTINGS

OK = "ok"
WARN = "warn"
RED = "red"
SKIP = "skip"
STATUSES = (OK, WARN, RED, SKIP)

# Every file a hook entry can be installed into, as a path relative to a root. The set is
# load-bearing twice — `setup` writes `USER_SETTINGS` and this check reads all three — so
# `USER_SETTINGS` is a *member* rather than a fourth spelling of the same name: a lane that
# moves it moves this walk with it. The two roots are the project (all three) and `home`
# (`USER_SETTINGS` alone, which is where `setup` merges the preset's deny rules).
SETTINGS_FILES = (
    USER_SETTINGS,
    ".claude/settings.local.json",
    ".codex/hooks.json",
)
# Where the harness reads Keelline's wrapper from, relative to the plugin root. `hooks/` stays
# at the plugin root — `overlay/template.py` says why — so it is found by environment or by
# checkout probe and never through `importlib.resources`.
WRAPPER = "hooks/run-hook.sh"
# A refusal token the wrapper prints: `KL_ARGV`, `KL_NO_PY`, `KL_NO_LAUNCHER`, `KL_RC`. The
# wrapper's own vocabulary, which is the whole reason it prints one — an exit 2 is attributed
# rather than inferred, and under `open` policy the exit code is 0 and the token is all there is.
_TOKEN = re.compile(r"\bKL_[A-Z_]+\b")
# Wall-clock bound on the one subprocess this area runs. D7 asks a cap to name the shipped file
# that must change with it; there is none, because this bounds `keelline --version` behind an
# interpreter probe and nothing about it is a project's to tune. Wide enough for a cold
# interpreter start on a loaded machine, narrow enough that a hung probe does not hang `doctor`.
WRAPPER_TIMEOUT_SECONDS = 30
# How much of a claimed marker id is printed; see the module docstring for why any of it is.
MARKER_ID_CHARS = 64
# Diagnostic records read back from the sink, newest last. The file is capped at
# `DIAGNOSTICS_MAX_BYTES` and rotated, so this bounds the report rather than the file.
DIAGNOSTICS_SHOWN = 5
# The three fields of a diagnostic record that are Keelline's own vocabulary. `context` and
# `decision` are not on this list on purpose: `dispatch._failure` fills them from a handler's
# own return value, which is the one part of that record a repository can reach.
DIAGNOSTIC_FIELDS = ("event", "handler", "error")


@dataclass(frozen=True)
class Check:
    """One row of the report: what was asked, what the answer was, and what to do about it.

    `remedy` is empty for a row nothing can be done about — an `ok`, or a `skip` whose reason is
    that this build cannot answer. A reader is never handed a command that would not help.
    """

    name: str
    status: str
    detail: str
    remedy: str = ""


@dataclass
class Context:
    """Everything the fifteen checks read, resolved once.

    Built by `run_checks` after `not-initialised` has passed, so `config` is never `None` here:
    a repository whose configuration does not load has nothing else worth asking about, and the
    first check says so and the rest skip.
    """

    root: Path
    home: Path | None
    machine: Path | None
    runner: Runner
    candidates: str | None
    env: Mapping[str, str]
    config: Config
    store: Store | None = None
    store_refusal: str | None = None
    plugin_root: Path | None = None
    overlay: Path | None = None


def plugin_root(env: Mapping[str, str]) -> Path | None:
    """Where `hooks/run-hook.sh` is on this machine, or `None` when it cannot be found.

    The harness's own variable first, because in a session that is the authoritative answer and
    the only one that holds for an installed plugin; a checkout second, for a developer running
    `scripts/keelline` out of the tree. A wheel carries neither — `hooks/` is outside the module
    root by design — so `None` is an ordinary answer here and the two checks that need it skip.
    """
    for name in ("CLAUDE_PLUGIN_ROOT", "PLUGIN_ROOT"):
        named = env.get(name)
        if named and (Path(named) / WRAPPER).is_file():
            return Path(named)
    checkout = Path(keelline.__file__).resolve().parents[2]
    return checkout if (checkout / WRAPPER).is_file() else None


def _not_initialised(context: Context) -> Check:
    # Reached only when the configuration loaded, so this row is the green one; the red one is
    # built by `run_checks` before a context exists at all.
    return Check("not-initialised", OK, f"{CONFIG_FILE} loads", "")


def _versions(context: Context) -> Check:
    running = keelline.__version__
    if context.config.keelline.version == running:
        return Check("versions", OK, f"the project and this Keelline are both {running}", "")
    # The project's own string is repository-authored and is not quoted back; what is printed
    # is the version that is actually running, which is what the remedy needs anyway.
    return Check(
        "versions",
        WARN,
        f"{CONFIG_FILE} declares a different Keelline version from the {running} running here",
        f"set [keelline] version to {running} in {CONFIG_FILE}",
    )


def _files(context: Context) -> Check:
    """§5.9 and Task 1: the shipped files, and the bit that decides whether one can run.

    The hash half cannot run in this build — the release lane records the hashes — and inventing
    a source for them would produce a check that compares a file against itself. The executable
    bit needs nothing but the file, so it runs regardless: a wrapper without `+x` exits 126, and
    Claude Code reads every non-2 exit as a non-blocking error, which is permission.
    """
    root = context.plugin_root
    if root is None:
        return Check(
            "files",
            SKIP,
            "the plugin root is not readable from here, so its shipped files cannot be checked",
            "",
        )
    wrapper = root / WRAPPER
    if not os.access(wrapper, os.X_OK):
        return Check(
            "files",
            RED,
            f"{WRAPPER} is not executable, so every hook entry exits 126 and the harness reads "
            f"that as a non-blocking error",
            f"chmod +x {wrapper}",
        )
    return Check(
        "files",
        SKIP,
        f"{WRAPPER} is executable; no release hashes are recorded in this build, so the "
        f"installed files cannot be compared against a release",
        "",
    )


def _wrapper(context: Context) -> Check:
    """Execute the wrapper once, and report the token it printed.

    §8.4 does not name this check and it closes a measured blind spot. Under `open` policy a
    failed interpreter probe prints to stderr and exits **0**; the harness discards stderr on a
    0; no Python ran, so nothing reached the sink; and `doctor` itself runs under whatever
    interpreter the user invoked it with rather than under the wrapper's candidate list. On a
    machine where the probe fails, every bundle is silently absent and all three diagnostic
    surfaces are blind. One subprocess closes it.

    `--version` and not a hook event: the point is whether the wrapper can reach Keelline at
    all, and the cheapest question that proves it is the one that changes nothing.
    """
    root = context.plugin_root
    if root is None:
        return Check("wrapper", SKIP, "the plugin root is not readable from here", "")
    env = {
        key: value
        for key, value in context.env.items()
        if not key.startswith(("CLAUDE_", "PLUGIN_", "KEELLINE_"))
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(root)
    env["CLAUDE_PROJECT_DIR"] = str(context.root)
    if context.candidates is not None:
        env["KEELLINE_PYTHON_CANDIDATES"] = context.candidates
    try:
        done = subprocess.run(  # noqa: S603 - list form, never a shell; Keelline's own wrapper
            [str(root / WRAPPER), "open", "--version"],
            cwd=context.root,
            capture_output=True,
            text=True,
            check=False,
            timeout=WRAPPER_TIMEOUT_SECONDS,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Check(
            "wrapper",
            RED,
            f"{WRAPPER} could not be run ({type(exc).__name__}), so no hook entry can fire",
            f"check that {root / WRAPPER} exists and is executable",
        )
    token = _TOKEN.search(done.stderr)
    if token is not None:
        return Check(
            "wrapper",
            RED,
            f"{WRAPPER} refused with {token.group(0)} and exited {done.returncode}; under "
            f"`open` policy that exit code is 0 and nothing else reports it",
            "run `hooks/run-hook.sh open --version` and read its stderr",
        )
    if done.returncode != 0:
        return Check(
            "wrapper",
            RED,
            f"{WRAPPER} exited {done.returncode} with no refusal token",
            "run `hooks/run-hook.sh open --version` and read its stderr",
        )
    return Check("wrapper", OK, f"{WRAPPER} reached Keelline and exited 0", "")


def _attach_ledger_entries(root: Path) -> dict[str, str]:
    """The marker ids this repository's last `attach` claims, or none when it never ran."""
    if not (root / LEDGER).is_file():
        return {}
    return dict(ledger(root).entries)


def _attached(context: Context) -> Check:
    """Attach state, and the shape of the harness memory path (§8.4, §12).

    §6.3 prefers a symlink at `~/.claude/projects/<slug>/memory` "because a settings-file value
    is subject to workspace trust and a link is not". A **real directory** there is §12's own
    row and the reason this check exists rather than a general "not attached": the harness's
    native reader finds a directory, reads nothing out of it, and reports no fault — it looks
    attached and behaves like nothing.

    A path that is simply absent is not that. `worktree.harness_link_needed` gates the link on
    the same trust record every other channel is gated on, so an unapproved store correctly has
    no link, and calling that red would make `doctor` red on a correct fresh install.
    """
    config = context.config
    if config.memory.mode != "overlay":
        # `memory.mode` is repository-authored and is safe to print for one reason only: the
        # loader holds it to a fixed set of three words, so what reaches this line is one of
        # Keelline's own labels rather than a string a clone chose.
        return Check(
            "attached", OK, f"memory.mode is {config.memory.mode}; there is no overlay to bind to"
        )
    recorded = (context.root / LEDGER).is_file()
    harness = harness_memory_path(context.root, context.home)
    if harness.is_dir() and not harness.is_symlink():
        return Check(
            "attached",
            RED,
            "the harness memory path is a real directory rather than a link to the store, so "
            "this checkout looks attached and behaves like nothing",
            # `<project>` and not `config.project.name`: the name is repository-authored, and a
            # remedy is as much output as a detail is.
            f"remove {harness} and run "
            f"`keelline attach --store <overlay>/{PROJECTS}/<project>/memory`",
        )
    if not recorded:
        return Check(
            "attached",
            WARN,
            f"memory.mode is overlay and {LEDGER} does not exist, so nothing records an attach",
            "run `keelline attach --store <overlay>/projects/<project>/memory --check`",
        )
    shape = "a link to the store" if harness.is_symlink() else "not in place"
    state = _binding_state(context)
    if state == MISMATCH:
        return Check(
            "attached",
            RED,
            "the overlay records a different remote for this project, so this is not the "
            "repository it was bound to",
            "run `keelline attach --check`, and `--trust-remote` only if it should be",
        )
    detail = f"attached; the harness memory path is {shape}"
    if state is not None:
        detail = f"{detail}; the binding is {state}"
    return Check("attached", OK, detail)


def _binding_state(context: Context) -> str | None:
    """The overlay binding's own label, or `None` when it cannot be asked on this machine.

    `read_binding` needs `git` and the recorded store, and it refuses a store that is not this
    project's share of the recorded overlay. A `doctor` that turned any of those into a red row
    would be reporting on its own inputs rather than on the installation.
    """
    try:
        store = Path(ledger(context.root).store)
        return read_binding(context.root, store=store, machine=context.machine).state
    except (Failure, Refusal, GitUnavailable):
        return None


def _entry_commands(document: str) -> list[str]:
    """Every hook command in a settings-shaped document, whoever wrote it, read defensively.

    `scaffold.owned_ids` refuses a shape it cannot read, which is right for a merge and wrong
    here: `doctor` is what a user has left when the file is broken, and counting the entries it
    can see is more use than refusing the row. Nothing is written from this walk.
    """
    try:
        raw = json.loads(document) if document.strip() else {}
    except json.JSONDecodeError:
        return []
    hooks = raw.get("hooks") if isinstance(raw, dict) else None
    found: list[str] = []
    for groups in hooks.values() if isinstance(hooks, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            entries = group.get("hooks") if isinstance(group, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                command = entry.get("command") if isinstance(entry, dict) else None
                if isinstance(command, str):
                    found.append(command)
    return found


def _hook_entries(context: Context) -> Check:
    """Every entry in every settings file, with provenance (§5.3, §12).

    Three provenances, and the third is the one §12 asks for. An id in the attach ledger is the
    overlay's; an entry with no marker is foreign and is left alone by every merge this project
    ships; an entry that **claims** the marker and is in no ledger is a repository saying it is
    Keelline, which is a stronger statement than "foreign" and the one a reader needs.
    """
    recorded = _attach_ledger_entries(context.root)
    claimed = 0
    foreign = 0
    unrecorded: list[str] = []
    walked = [(context.root, relative) for relative in SETTINGS_FILES]
    if context.home is not None:
        walked.append((context.home, USER_SETTINGS))
    for base, relative in walked:
        path = base / relative
        if not path.is_file():
            continue
        try:
            document = path.read_text(encoding="utf-8")
        except OSError:
            continue
        commands = _entry_commands(document)
        try:
            ids = owned_ids(document)
        except Refusal:
            ids = {}
        claimed += len(ids)
        foreign += len(commands) - len(ids)
        unrecorded += [
            f"{relative}: keelline:{entry_id[:MARKER_ID_CHARS]}"
            for entry_id in sorted(ids)
            if entry_id not in recorded
        ]
    counted = f"{claimed} keelline entr(ies), {foreign} foreign"
    if unrecorded:
        return Check(
            "hook-entries",
            RED,
            f"{counted}; {len(unrecorded)} claim(s) the Keelline marker that {LEDGER} does not "
            f"record: {listed(unrecorded)}",
            "read each entry named above and remove the ones you did not install",
        )
    return Check("hook-entries", OK, f"{counted}, all accounted for")


def _codex_trust(context: Context) -> Check:
    # §5.3 asks for red while any Keelline hook is untrusted on Codex, and §10 lists the Codex
    # hook-trust hash under what these spikes did not measure. A check that returned green
    # because it could not look would be strictly worse than one that admits it cannot.
    return Check(
        "codex-trust",
        SKIP,
        "whether a Keelline hook is trusted on Codex is unmeasured: nothing here knows how "
        "Codex records hook trust, and a measurement would need the file it writes it to and "
        "the hash it keys on",
        "",
    )


def _budgets(context: Context) -> Check:
    """Every budget overriding the preset, and every one the ceiling clamps (D7, §9.5).

    A value above the preset's is ignored rather than refused, which is what makes lowering the
    only direction — and also what makes the number in the file silently not the number in
    force. Budget keys are `Budgets.NAMES` and the loader refuses any other, so these are
    Keelline's own names rather than a repository's strings.
    """
    budgets = context.config.budgets
    clamped = sorted(
        name
        for name, value in budgets.configured.items()
        if value > budgets.preset.get(name, value)
    )
    overrides = sorted(budgets.overrides)
    if clamped:
        return Check(
            "budgets",
            WARN,
            f"{len(clamped)} budget(s) are set above the preset and are clamped down to it: "
            f"{listed(clamped)}",
            f"lower these values in {CONFIG_FILE}, or delete them to take the preset's",
        )
    if overrides:
        return Check("budgets", OK, f"{len(overrides)} budget(s) lowered: {listed(overrides)}")
    return Check("budgets", OK, "every budget is the preset's")


# When a bundle's largest part counts as "reaching the cap", as a fraction of
# `native_caps.hook_output_chars`. §9.5 asks `doctor` to report a bundle that does not fit *and*
# one that reaches the cap, and the second needs a threshold that the first does not.
#
# A fraction and not `parts == slots`: `preset-rules` has one slot and any preset at all fills
# it, so that predicate warns on every correct installation and says nothing. D7 asks a cap to
# name the shipped file that must change with it — this one names `hooks/hooks.json`, which is
# where a slot count is raised when this warning turns out to be right.
NEARLY_FULL = 0.9


def _bundles(context: Context) -> Check:
    """§9.5: a bundle whose notes do not fit its slots needs a human, not a wider cap.

    Raising a slot count edits `hooks/hooks.json`, which is a shipped file, so this is reported
    and never repaired. A part already close to the platform cap is the warning before that:
    one more sentence in one note and the bundle needs a slot that does not exist.
    """
    if context.store is None:
        return Check("bundles", SKIP, "the note store does not resolve, so no bundle can be built")
    ceiling = context.config.native_caps.hook_output_chars * NEARLY_FULL
    over: list[str] = []
    full: list[str] = []
    for bundle in SLOTS:
        measured = fit(bundle, context.store, context.config)
        if not measured.fits:
            over.append(bundle.value)
            continue
        emitted = [
            render(bundle, context.store, context.config, part=n)
            for n in range(1, measured.parts + 1)
        ]
        if any(text is not None and len(text) >= ceiling for text in emitted):
            full.append(bundle.value)
    if over:
        return Check(
            "bundles",
            RED,
            f"{len(over)} bundle(s) do not fit their session-start slots: {listed(over)}",
            "run `keelline memory fit`, then shorten or unflag the notes it names",
        )
    if full:
        return Check(
            "bundles",
            WARN,
            f"{len(full)} bundle(s) have a part at the platform cap: {listed(full)}",
            "run `keelline memory fit`",
        )
    return Check("bundles", OK, "every bundle fits its slots")


def _cli_path(context: Context) -> Check:
    # §5.1 and Findings → S2: Codex performs no `${CLAUDE_PLUGIN_ROOT}` substitution in skill
    # content, so a skill that says `keelline …` needs the name to resolve on PATH there.
    found = shutil.which("keelline")
    if found is None:
        return Check(
            "cli-path",
            WARN,
            "`keelline` does not resolve on PATH, so a skill that invokes it by name fails on "
            "Codex, which performs no plugin-root substitution in skill content",
            "run `uv tool install git+https://github.com/Nezhinskiy/keelline`",
        )
    return Check("cli-path", OK, f"`keelline` resolves on PATH at {found}")


# The overlay's commit-time secret scan, and the hook `pre-commit install` writes (§6.4).
PRE_COMMIT_CONFIG = ".pre-commit-config.yaml"
PRE_COMMIT_HOOK = Path(".git") / "hooks" / "pre-commit"


def _pre_commit(context: Context) -> Check:
    """§6.4, §8.4: whether the overlay's own secret scan is armed on **this** machine.

    `overlay init` runs `pre-commit install` on the machine that created the overlay; a second
    machine clones that overlay and never runs `init` again, so the machine that thinks it is
    set up is exactly the one whose commit-time scan is not.
    """
    overlay = context.overlay
    if overlay is None or not overlay.is_dir():
        return Check("pre-commit", SKIP, "no overlay root is recorded on this machine", "")
    if not (overlay / PRE_COMMIT_CONFIG).is_file():
        return Check(
            "pre-commit",
            WARN,
            f"the overlay has no {PRE_COMMIT_CONFIG}, so there is no commit-time secret scan "
            f"for the notes it holds",
            "run `keelline overlay upgrade` to refresh the overlay's shipped files",
        )
    if not (overlay / PRE_COMMIT_HOOK).exists():
        return Check(
            "pre-commit",
            WARN,
            "the overlay's commit-time secret scan is configured and not installed on this "
            "machine; the push-time scan still runs",
            f"run `pre-commit install` in {overlay}",
        )
    return Check("pre-commit", OK, "the overlay's commit-time secret scan is installed")


def _ci_ref(context: Context) -> Check:
    """§8.4: whether `[ci] ref` resolves, asked with `git ls-remote --exit-code`.

    The value is repository-authored, so it is passed to the runner after a `--` and is never
    printed — not in the detail, not in the remedy. `init` is the lane that writes it (wave 5),
    so an empty value is `skip` rather than red: nothing in this build has had a chance to set
    one, and calling that a fault would make `doctor` red on every correct installation.
    """
    ref = context.config.ci.ref
    if not ref:
        return Check("ci-ref", SKIP, "no [ci] ref is recorded, so there is nothing to resolve", "")
    done = context.runner.run(["git", "ls-remote", "--exit-code", "--", ref], context.root)
    if done.code == 0:
        return Check("ci-ref", OK, "[ci] ref resolves")
    if done.code == 2:
        return Check(
            "ci-ref",
            RED,
            "[ci] ref does not resolve, so the reusable workflow this project pins is not there",
            f"correct [ci] ref in {CONFIG_FILE}",
        )
    return Check(
        "ci-ref",
        WARN,
        f"[ci] ref could not be checked (`git ls-remote` exited {done.code})",
        "check that `git` runs here and that the remote is reachable",
    )


def _store_debris(context: Context) -> Check:
    """§8.4: files in the note store that are not notes.

    Counted and not named. A filename in the store is repository-authored in `in-repo` and
    `local-only` mode — the two the preset ships — so the count is this lane's own answer and
    the remedy names the command that lists them under the trust gate.
    """
    store = context.store
    if store is None:
        return Check("store-debris", SKIP, "the note store does not resolve", "")
    found = 0
    for target in store.groups.values():
        for path in target.rglob("*"):
            if path.is_file() and path.suffix != ".md" and not path.name.startswith("."):
                found += 1
    if found:
        return Check(
            "store-debris",
            WARN,
            f"{found} file(s) in the note store are not notes",
            "run `keelline memory inventory` to see them, and move or delete each one",
        )
    return Check("store-debris", OK, "the note store holds notes and nothing else")


def _diagnostics(context: Context) -> Check:
    """The last reasons the hook sink recorded — reasons, never payloads (§5.3).

    Three fields are printed and the rest of the record is dropped: `event`, `handler` and
    `error` are Keelline's own vocabulary, while `context` and `decision` are filled from a
    handler's own return value by `dispatch._failure` and are the one part of this record a
    repository can reach. The sink already caps every field; printing the whole record would
    undo that cap rather than inherit it.
    """
    data = context.env.get("CLAUDE_PLUGIN_DATA") or context.env.get("PLUGIN_DATA")
    if not data:
        return Check(
            "diagnostics",
            SKIP,
            "no harness data root is set in this environment, so the hook sink cannot be read",
            "",
        )
    base = Path(data) / DIRECTORY
    sessions = len(list((base / MARKERS).iterdir())) if (base / MARKERS).is_dir() else 0
    log = base / DIAGNOSTICS
    if not log.is_file():
        return Check(
            "diagnostics", OK, f"no hook failures are recorded; {sessions} session(s) seen"
        )
    reasons: list[str] = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            reasons.append(" ".join(str(record.get(field_, "-")) for field_ in DIAGNOSTIC_FIELDS))
    if not reasons:
        return Check(
            "diagnostics", OK, f"no hook failures are recorded; {sessions} session(s) seen"
        )
    return Check(
        "diagnostics",
        WARN,
        f"{len(reasons)} hook failure(s) recorded; the last "
        f"{min(len(reasons), DIAGNOSTICS_SHOWN)}: {listed(reasons[-DIAGNOSTICS_SHOWN:])}",
        "each line above is event, handler and error type; run the named command by hand to "
        "see the failure in full",
    )


# The two variables that can name the machine configuration file, and are honoured only from an
# interactive shell. `config/machine.py` nominates this check by name: "a machine owner who sets
# one really does lose it on the hook path rather than getting a wrong answer quietly".
IGNORED_ENV = ("KEELLINE_CONFIG", "XDG_CONFIG_HOME")


def _ignored_env(context: Context) -> Check:
    set_here = [name for name in IGNORED_ENV if context.env.get(name)]
    if not set_here:
        return Check("ignored-env", OK, "no environment variable is being ignored")
    return Check(
        "ignored-env",
        WARN,
        f"{listed(set_here)} is set and is not honoured on the hook path: the machine "
        f"configuration is ~/.config/keelline/config.toml and nothing else there",
        "pass --machine <path> to a command that must read a different file",
    )


# The fifteen, in the order §8.4 and its cross-references name them. The list is the report's
# order and the only registry there is: a check added here needs no other edit, and a check
# missing from it is a check nothing runs.
CHECKS: tuple[tuple[str, Callable[[Context], Check]], ...] = (
    ("not-initialised", _not_initialised),
    ("versions", _versions),
    ("files", _files),
    ("wrapper", _wrapper),
    ("attached", _attached),
    ("hook-entries", _hook_entries),
    ("codex-trust", _codex_trust),
    ("budgets", _budgets),
    ("bundles", _bundles),
    ("cli-path", _cli_path),
    ("pre-commit", _pre_commit),
    ("ci-ref", _ci_ref),
    ("store-debris", _store_debris),
    ("diagnostics", _diagnostics),
    ("ignored-env", _ignored_env),
)


def _guarded(name: str, check: Callable[[Context], Check], context: Context) -> Check:
    """One check's answer, or a red row naming the exception type it died of.

    Never a traceback out of `run_checks`. The report is the thing the user has left when
    everything else is broken, so a check that raises costs one row and not the diagnosis — and
    the exception's *message* is not printed, because a `Failure` built out of `memory.groups`
    or a note's path is repository-authored by the Global Constraints' own list.
    """
    try:
        return check(context)
    except BaseException as exc:  # a broken check must cost one row, never the whole report
        return Check(
            name,
            RED,
            f"this check could not run: {type(exc).__name__}",
            "report this, with the command you ran",
        )


def _context(
    root: Path,
    *,
    home: Path | None,
    machine: Path | None,
    runner: Runner,
    candidates: str | None,
    env: Mapping[str, str],
    config: Config,
) -> Context:
    context = Context(root, home, machine, runner, candidates, env, config)
    context.plugin_root = plugin_root(env)
    try:
        context.overlay = overlay_root(machine)
    except Failure:
        context.overlay = None
    try:
        context.store = resolve(root, config, machine=machine)
    except (Failure, Refusal, OSError):
        context.store = None
    return context


def run_checks(
    root: Path,
    *,
    home: Path | None,
    machine: Path | None,
    runner: Runner,
    candidates: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[Check]:
    """The fifteen rows, always fifteen, whatever state the machine is in.

    `candidates` is the wrapper's `KEELLINE_PYTHON_CANDIDATES` list, threaded so that a test can
    ask what happens when the interpreter probe fails without arranging a machine with no
    Python. The plan's `Interfaces:` block names four keyword parameters and its own test for
    the `wrapper` check passes a fifth; this is that fifth, defaulted so the four-parameter form
    in the block is the real signature.

    `env` defaults to the process environment because two checks are *about* the environment —
    `ignored-env` reads it, and `diagnostics` finds the harness data root in it.
    """
    env = os.environ if env is None else env
    rest = [name for name, _ in CHECKS[1:]]
    if not (root / CONFIG_FILE).is_file():
        return [
            Check(
                "not-initialised",
                RED,
                f"there is no {CONFIG_FILE} here, so the plugin's hooks are silent in this "
                f"repository",
                "run `keelline init` once it ships, or write keelline.toml by hand",
            ),
            *(
                Check(name, SKIP, f"there is no {CONFIG_FILE} to check against", "")
                for name in rest
            ),
        ]
    try:
        config = load(root, machine=machine)
    except (Failure, Refusal) as exc:
        # The message is not quoted: the loader builds it out of the file's own keys and values.
        return [
            Check(
                "not-initialised",
                RED,
                f"{CONFIG_FILE} is here and does not load ({type(exc).__name__}), so nothing "
                f"else can be checked against it",
                f"run `keelline doctor` again after fixing {CONFIG_FILE}",
            ),
            *(Check(name, SKIP, f"{CONFIG_FILE} does not load", "") for name in rest),
        ]
    context = _context(
        root,
        home=home,
        machine=machine,
        runner=runner,
        candidates=candidates,
        env=env,
        config=config,
    )
    return [_guarded(name, check, context) for name, check in CHECKS]
