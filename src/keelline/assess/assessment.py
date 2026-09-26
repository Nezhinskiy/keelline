"""What stands between a repository, as it is, and enforcement: every configured gate and every
probe, as one inventory.

**The tree's own configuration.** The question is about this tree, so `assess` reads the tree's
`keelline.toml` and is not a trust boundary: what a clone configures is what a person running
it asked to see judged, the way running its test suite runs the tests it carries.

**Compute everything, then write once.** Every gate and probe runs before the one write, so a
run that stops part-way leaves the last finished inventory in place rather than half of a new
one.

The file is read through the reader `keelline gate` uses, which refuses a `keelline.toml` that
is a symlink: a clone's link to `/dev/zero` would otherwise end the run by exhausting memory.

**One write, at a constant place.** The inventory goes to `ASSESSMENT`, Keelline's own spelling
of the path `keelline uninstall` takes back, and no configured value can move it: the loader
refuses a `[paths]` value inside Keelline's directory. What a clone can do is put something
there — a symlinked `.keelline`, or a directory at the file's place — and each is a refusal
with nothing written. A symlink at the file's place is replaced by the file and its target is
left as it was, because the replacement is a rename, which never follows a link at its
destination.

**Counts in the summary, the rest in the document.** A gate's reason, a custom gate's output
and every item's `where` can carry what a repository authored, so `render` prints counts and
Keelline's own words — gate names, probe and rule ids, severities, remedies — and the whole
list goes to the file and `--json`, which are one serialisation (`document`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import keelline
from keelline.assess.gates import Gate, GateContext, GateResult, configured, run_gates
from keelline.assess.model import Item, item
from keelline.assess.probes import ProbeContext, run_probes
from keelline.config.layout import local_base
from keelline.config.loader import CONFIG_FILE, NOT_THERE, ConfigError, loads, read_document
from keelline.errors import Refusal
from keelline.findings import Severity
from keelline.fsops import UnsafePath, write_within
from keelline.gitenv import git_run
from keelline.project.api import ASSESSMENT

FORMAT = 1

UNWRITABLE = (
    f"refusing to write {ASSESSMENT}: a directory on its path is a symlink or not a directory; "
    "remove it and re-run"
)
NOT_A_FILE = (
    f"refusing to write {ASSESSMENT}: something that is not a file is there; remove it and re-run"
)
NOT_IGNORED = (
    f"note: git does not ignore {ASSESSMENT} here, and it lists this repository's paths; the "
    "keelline:ignore region `keelline init` writes into .gitignore keeps it out of git"
)


@dataclass(frozen=True)
class Assessment:
    base: str
    state: str
    enforcing: tuple[str, ...]
    gates: tuple[GateResult, ...]
    items: tuple[Item, ...]

    @property
    def would_fail(self) -> tuple[str, ...]:
        """Every failing gate, enforced or not: what enforcing it now would stop."""
        return tuple(g.name for g in self.gates if g.failing)


def _gate_items(gate: Gate, result: GateResult) -> Iterator[Item]:
    """One item per rule the gate's findings carry, in first-seen order, at `warning`."""
    by_rule: dict[str, list[str]] = {}
    for finding in result.findings:
        by_rule.setdefault(finding.rule, []).append(finding.label)
    for rule, labels in by_rule.items():
        yield item(gate.name, rule, gate.principle, Severity.WARNING, gate.remedy, labels)


def assess(root: Path, *, machine: Path | None, base: str | None) -> Assessment:
    """Every configured gate against `base`, then every probe, over the tree at `root`."""
    from keelline.presets import load_preset

    text = read_document(root)
    if text is None:
        raise ConfigError(NOT_THERE.format(path=root / CONFIG_FILE))
    config = loads(text, root, machine=machine)
    base = base or local_base(config)
    results = run_gates(GateContext(root, config, base), config.gate_names)
    gates = configured(config)
    window = int(load_preset(config.keelline.preset)["assess"]["commit_window"])
    items = [i for r in results for i in _gate_items(gates[r.name], r)]
    items += run_probes(ProbeContext(root, config, window))
    enforcing = tuple(n for n in config.gate_names if n in config.keelline.enforcing)
    return Assessment(base, config.keelline.state, enforcing, results, tuple(items))


def document(assessment: Assessment) -> dict[str, Any]:
    """The one serialisation: the file's contents, and `--json`'s object beside its summary."""
    return {
        "format": FORMAT,
        "keelline": keelline.__version__,
        "base": assessment.base,
        "state": assessment.state,
        "enforcing": list(assessment.enforcing),
        "gates": [
            {
                "name": g.name,
                "enforcing": g.name in assessment.enforcing,
                "answered": g.answered,
                "reason": g.reason,
                "count": len(g.findings),
                "failing": g.failing,
            }
            for g in assessment.gates
        ],
        "items": [
            {
                "probe": i.probe,
                "rule": i.rule,
                "principle": i.principle,
                "severity": i.severity.value,
                "remedy": i.remedy,
                "where": list(i.where),
                "count": i.count,
            }
            for i in assessment.items
        ],
    }


def write(root: Path, assessment: Assessment) -> None:
    """The inventory at `ASSESSMENT`, through the walk that refuses a symlinked directory.

    `rename(2)` answers `EISDIR` for a file renamed over a directory, which Python raises as
    `IsADirectoryError`: a directory at the file's place is never replaced.
    """
    text = json.dumps(document(assessment), indent=2, sort_keys=True) + "\n"
    try:
        write_within(root, ASSESSMENT, text)
    except UnsafePath:
        raise Refusal(UNWRITABLE) from None
    except IsADirectoryError:
        raise Refusal(NOT_A_FILE) from None


def ignored(root: Path) -> bool | None:
    """Whether git ignores `ASSESSMENT` here; `None` when git gives no answer."""
    code, _ = git_run(root, "check-ignore", "-q", "--", ASSESSMENT)
    return {0: True, 1: False}.get(code)


def render(assessment: Assessment) -> str:
    """The markdown summary: every cell is Keelline's own or a profile's, never a path the
    repository chose."""
    failing = assessment.would_fail
    lines = [
        f"assessment: state {assessment.state}; {len(failing)} of {len(assessment.gates)} "
        f"gate(s) would fail if enforced; {len(assessment.items)} item(s); the whole list is in "
        f"{ASSESSMENT}",
        "",
        "| gate | enforcing | findings | would fail |",
        "|---|---|---|---|",
    ]
    for g in assessment.gates:
        count = len(g.findings) if g.answered else "could not run"
        lines.append(
            f"| {g.name} | {'yes' if g.name in assessment.enforcing else 'no'} | {count} | "
            f"{'yes' if g.failing else 'no'} |"
        )
    if assessment.items:
        lines += ["", "| from | rule | severity | count | remedy |", "|---|---|---|---|---|"]
        lines += [
            f"| {i.probe} | {i.rule} | {i.severity.value} | {i.count} | {i.remedy} |"
            for i in assessment.items
        ]
    return "\n".join(lines)
