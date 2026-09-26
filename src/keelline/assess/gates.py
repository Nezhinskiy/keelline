"""Every configured gate as a value: each built-in is its own area's gate function, and a
project's custom gate is the argv its `[gates.custom.<name>] run` configures.

A built-in's composition lives once, in its area, and that area's command answers with the same
function or with the one call it wraps, so what `run_gates` judges and what a person runs cannot
drift apart. Every gate takes `(root, config, base)`, so each one is a value here whether it
reads the base or not.

A gate that could not judge the tree is not a passing gate: its result is `answered=False`, and
`failing` counts it. Its `reason` is fixed text built from the gate's own command, its name and
the configured bound, never from an exception's text or the base, because both can carry what a
repository authored. A custom gate's output goes to this process's standard error as it ran and
is read by nothing here, so none of it reaches a result.

**A custom gate's process group ends with it.** Its command runs in a session of its own, and
that session's process group is ended however the command finishes — exit, timeout or
interrupt — so nothing it left in the background in that group writes into the tree while a later
gate runs or after the result is out. A descendant that starts a session of its own (`setsid`)
has left the group, and is not reached.

**Order.** The built-ins run first, in configured order: they execute nothing the repository
wrote. Then the custom gates the caller names in `first`, then every other custom gate. A custom
gate executes files the change can edit, so one that ran earlier could rewrite what a later one
executes; `keelline gate` names the base's enforced gates in `first`, so no other custom gate
runs before them.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from keelline.docs.api import docs_gate, plan_gate, trail_gate
from keelline.errors import KeellineError
from keelline.findings import Finding
from keelline.guards.api import commit_gate
from keelline.ledger.api import bugs_gate

if TYPE_CHECKING:
    from keelline.config.schema import Config

BASE = "<base>"  # where the base goes in a gate's command; the base itself is never printed

COULD_NOT_RUN = "could not judge this tree; `keelline {command}` names the cause"
CUSTOM_COULD_NOT_RUN = (
    "the command [gates.custom.{name}] run names could not start, or ran past {seconds}s"
)
CUSTOM_REMEDY = "fix what [gates.custom.{name}] run reports; its output is printed as it ran"

# Reaping a command whose group was sent SIGKILL. The signal cannot be caught or ignored, so this
# is slack for the kernel, not a second bound on the command.
KILL_WAIT_SECONDS = 5


@dataclass(frozen=True)
class GateContext:
    root: Path
    config: Config
    base: str


@dataclass(frozen=True)
class GateResult:
    name: str
    findings: tuple[Finding, ...]
    answered: bool = True
    reason: str = ""

    @property
    def failing(self) -> bool:
        """A finding fails the gate, and so does a gate that could not judge the tree."""
        return bool(self.findings) or not self.answered


@dataclass(frozen=True)
class Gate:
    name: str
    principle: int | None
    remedy: str
    command: str  # what a person runs for this gate, with BASE where the base goes
    run: Callable[[Path, Config, str], list[Finding]]


BUILTIN: tuple[Gate, ...] = (
    Gate(
        "docs",
        None,
        "run `keelline docs check` and fix each finding; a checked document kept out of git "
        "([artifacts] local) drops docs from [gates] builtin instead",
        "docs check",
        docs_gate,
    ),
    Gate("bugs", 1, "run `keelline bugs check` and fix each finding", "bugs check", bugs_gate),
    Gate(
        "plan",
        2,
        f"run `keelline plan check --base {BASE}` and fix each plan it names",
        f"plan check --base {BASE}",
        plan_gate,
    ),
    Gate(
        "commit",
        None,
        "rewrite the named commits' messages without their attribution lines",
        f"commit check --range {BASE}..HEAD",
        commit_gate,
    ),
    Gate(
        "trail",
        None,
        "run `keelline docs trail` and commit the roadmap it rewrites; a roadmap kept out of "
        "git ([artifacts] local) drops trail from [gates] builtin instead",
        "docs trail --check",
        trail_gate,
    ),
)


class _NotAnswered(Exception):
    """A custom gate that did not finish. `reason` is built from bounded values only."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    """SIGKILL the command's whole process group; a group with nothing left to end is no fault.

    Empty, the group answers `ProcessLookupError`; left with only the exited, unreaped command,
    macOS answers `PermissionError` rather than nothing, as it does for any group of zombies.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGKILL)


def _exited(process: subprocess.Popen[bytes], seconds: int) -> None:
    """Return once the command has exited, leaving it unreaped where the platform allows it.

    The group's id is the command's pid, and a reaped pid is free for the system to hand to an
    unrelated process that then leads a group of its own, which a later `killpg` would end. An
    exited command that is not yet reaped keeps its pid taken, so `os.waitid` with `WNOWAIT`
    watches for the exit without reaping, the group is ended, and only then is the command
    reaped. Where `os.waitid` is missing (macOS before Python 3.13) the command is reaped here,
    as `Popen.wait` does, and the group is ended just after.

    Raises `subprocess.TimeoutExpired` past `seconds`, as `Popen.wait` does.
    """
    if not hasattr(os, "waitid"):
        process.wait(timeout=seconds)
        return
    deadline = time.monotonic() + seconds
    delay = 0.0005
    flags = os.WEXITED | os.WNOHANG | os.WNOWAIT
    while os.waitid(os.P_PID, process.pid, flags) is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, seconds)
        delay = min(delay * 2, remaining, 0.05)
        time.sleep(delay)


def _end(process: subprocess.Popen[bytes]) -> None:
    """End the command's whole process group and reap it, within `KILL_WAIT_SECONDS`."""
    _kill_group(process)
    process.wait(timeout=KILL_WAIT_SECONDS)


def _custom(name: str, argv: tuple[str, ...]) -> Callable[[Path, Config, str], list[Finding]]:
    def run(root: Path, config: Config, base: str) -> list[Finding]:
        seconds = config.gates.custom_timeout_seconds
        not_answered = _NotAnswered(CUSTOM_COULD_NOT_RUN.format(name=name, seconds=seconds))
        try:
            # S603: the project's own `[gates.custom.<name>] run`, list form, never a shell.
            # Both streams go to this process's standard error untouched, so a person and a CI
            # log see them as they ran and `--json` on standard output stays one object. A
            # session of its own puts what the command starts in one process group, unless a
            # descendant starts a session of its own, and that group is ended however the command
            # finishes: `subprocess.run(timeout=...)` kills the command alone, and a test runner
            # it started keeps writing after the gate has reported.
            process = subprocess.Popen(  # noqa: S603
                list(argv),
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=2,
                stderr=2,
                start_new_session=True,
            )
        except OSError:
            raise not_answered from None
        try:
            _exited(process, seconds)
        except subprocess.TimeoutExpired:
            _end(process)
            raise not_answered from None
        except BaseException:
            # A terminal's Ctrl-C reaches Keelline's process group, not the command's session,
            # so an interrupted run ends the command's tree itself before it leaves.
            _end(process)  # on an interrupt or any other exit, as subprocess.run's own kill did
            raise
        # The command has exited, and what it started may still run: a watcher or a server left
        # in the background, still writing into the tree while a later gate runs. The exited
        # command is not reaped yet, so the group's id is still its own and reaches only its
        # descendants; then it is reaped, which reads the status it exited with.
        _kill_group(process)  # after an exit of its own too
        code = process.wait()
        if code == 0:
            return []
        return [Finding("exit-status", "", None, f"exited {code}")]

    return run


def configured(config: Config) -> dict[str, Gate]:
    """Every gate `config` runs, by name, in `config.gate_names` order.

    A custom gate cites no principle, and its command is the one that runs it alone.
    """
    builtin = {gate.name: gate for gate in BUILTIN}
    gates: dict[str, Gate] = {}
    for name in config.gate_names:
        custom = config.gates.custom.get(name)
        if custom is None:
            gates[name] = builtin[name]
            continue
        gates[name] = Gate(
            name,
            None,
            CUSTOM_REMEDY.format(name=name),
            f"gate --only {name}",
            _custom(name, custom.run),
        )
    return gates


def _guarded(gate: Gate, context: GateContext) -> GateResult:
    try:
        found = gate.run(context.root, context.config, context.base)
    except _NotAnswered as exc:
        return GateResult(gate.name, (), False, exc.reason)
    except KeellineError:
        return GateResult(gate.name, (), False, COULD_NOT_RUN.format(command=gate.command))
    except RecursionError:
        # A backstop: every reader of a repository's TOML answers a document nested past the
        # parser's recursion as unreadable, and a reader that did not would end every gate.
        return GateResult(gate.name, (), False, COULD_NOT_RUN.format(command=gate.command))
    return GateResult(gate.name, tuple(found))


def run_gates(
    context: GateContext, names: Sequence[str], *, first: frozenset[str] = frozenset()
) -> tuple[GateResult, ...]:
    """A result for each configured gate `names` asks for, each run once: the built-ins and the
    custom gates `first` names, then every other custom gate, each group in configured order.

    One gate that does not answer never stops another. A name the configuration does not hold is
    a `KeyError`: callers validate names before they ask.
    """
    gates = configured(context.config)
    wanted = {gates[name].name for name in names}
    custom = context.config.gates.custom
    order = sorted(gates, key=lambda name: name in custom and name not in first)
    return tuple(_guarded(gates[name], context) for name in order if name in wanted)
