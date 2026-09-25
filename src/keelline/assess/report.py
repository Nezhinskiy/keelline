"""What a gate run hands a person: its exit code, the platform's workflow commands, and a job
summary.

**What prints.** Counts, gate names, modes, rule ids and changed key names: Keelline's own
vocabulary, or a name the loader bounded. A finding's `detail` can quote the repository and never
prints here. A finding's path is a name found on disk or in a diff, so it is written as an
annotation's `file=` only when it matches `PATH_VALUE`, the one grammar a path may print in;
escaping bounds a workflow command's shape, not its characters. The summary carries no path at
all.

**The platform's bound.** A step shows ten annotations per level and drops the rest without a
word, so every command goes through one emitter capped per level, and past the cap one
`::notice::` counts what was held back.

**What fails the run.** An enforced gate that is failing, and, when the configuration check ran,
a key the rule refused. An advisory gate's findings are annotated and never fail it.
"""

from __future__ import annotations

from dataclasses import dataclass

from keelline.assess.gates import GateResult
from keelline.assess.rule import ConfigVerdict, Verdict
from keelline.config.loader import CONFIG_FILE
from keelline.config.schema import PATH_VALUE

ANNOTATION_CAP = 10

REFUSED_KEY = "{key} may not change this way in a pull request"
HELD = "{count} more {level} annotation(s) not shown; the job summary counts them all"
BOOTSTRAP = "keelline.toml: the base has none at this path, so this tree's decides"
UNCHANGED = "keelline.toml: unchanged from the base"


@dataclass(frozen=True)
class GateRun:
    verdict: ConfigVerdict
    results: tuple[GateResult, ...]
    judged: bool  # whether the configuration check ran, and so whether a refusal counts
    prefix: str = ""  # the project root inside the repository, as `repository_prefix` gives it

    @property
    def blocking(self) -> tuple[str, ...]:
        """The enforced gates that are failing."""
        enforcing = self.verdict.enforcing
        return tuple(r.name for r in self.results if r.failing and r.name in enforcing)

    @property
    def exit_code(self) -> int:
        return 1 if self.blocking or (self.judged and self.verdict.refused) else 0


def _data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def workflow_commands(run: GateRun, *, cap: int = ANNOTATION_CAP) -> list[str]:
    """One `error` per refused key, then one annotation per finding or unanswered gate, `error`
    for an enforcing gate and `warning` for an advisory one, at most `cap` per level."""
    lines: list[str] = []
    shown = {"error": 0, "warning": 0}
    held = {"error": 0, "warning": 0}

    def emit(level: str, path: str, line: int | None, message: str) -> None:
        if shown[level] >= cap:
            held[level] += 1
            return
        shown[level] += 1
        where = ""
        located = run.prefix + path if path else ""
        # Printed only inside the one grammar a path may print in: a finding's path is a name
        # found on disk or in a diff, and escaping bounds a command's shape, not its characters.
        if located and PATH_VALUE.match(located):
            where = f" file={located}" + (f",line={line}" if line is not None else "")
        lines.append(f"::{level}{where}::{_data(message)}")

    if run.judged:
        for change in run.verdict.changes:
            if change.verdict is Verdict.REFUSED:
                emit("error", CONFIG_FILE, None, REFUSED_KEY.format(key=change.key))
    for result in run.results:
        level = "error" if result.name in run.verdict.enforcing else "warning"
        if not result.answered:
            emit(level, "", None, f"{result.name}: {result.reason}")
        # A `commit` finding's path is the commit's id, and the platform would look for a file.
        located_here = result.name != "commit"
        for finding in result.findings:
            path = finding.path if located_here else ""
            emit(level, path, finding.line, f"{result.name}: {finding.rule}")
    for level, count in held.items():
        if count:
            lines.append(f"::notice::{HELD.format(count=count, level=level)}")
    return lines


def _outcome(result: GateResult, enforcing: bool) -> str:
    if not result.failing:
        return "passes"
    return "fails" if enforcing else "would fail"


def summary(run: GateRun) -> str:
    """The job summary, as markdown: each gate's mode, count and outcome, then, when the
    configuration check ran, each changed key's verdict. Counts and names only."""
    blocks: list[list[str]] = []
    if run.results:
        rows = ["| gate | mode | findings | verdict |", "|---|---|---|---|"]
        for result in run.results:
            enforcing = result.name in run.verdict.enforcing
            count = len(result.findings) if result.answered else "could not run"
            mode = "enforcing" if enforcing else "advisory"
            rows.append(f"| {result.name} | {mode} | {count} | {_outcome(result, enforcing)} |")
        blocks.append(rows)
    if run.judged:
        if run.verdict.base_state is None:
            blocks.append([BOOTSTRAP])
        elif run.verdict.changes:
            rows = ["| keelline.toml key | verdict |", "|---|---|"]
            rows += [f"| {c.key} | {c.verdict.value} |" for c in run.verdict.changes]
            blocks.append(rows)
        else:
            blocks.append([UNCHANGED])
    return "\n\n".join("\n".join(block) for block in blocks) + "\n"
