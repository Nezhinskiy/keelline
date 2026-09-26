"""The adoption state machine: a project's gates move from advisory to enforcing one at a time,
each once it passes.

`[keelline] state` is the lifecycle (`initialised`, `adopting`, `installed`) and `enforced` the
gates promoted while adopting. `begin` checks an adoption plan and marks an `initialised`
project `adopting`; `promote` runs gates strictly on the tree as it is and adds those that pass
to `enforced`. Promoting the last configured gate writes `installed` and empties the list, which
under `installed` means every configured gate, so a gate added later enforces from its first
run. The state never moves back: there is no demotion, and loosening is an owner's edit of
`keelline.toml`, which `keelline gate` refuses to a pull request while anything enforces.

**One write, at one place.** Both verbs change `keelline.toml`'s `state` and `enforced` through
`rewrite_owned` and nothing else, so the manifest's record of an untouched document is
re-stamped with it and `uninstall` still takes the file back. Neither asks the ignore guard:
`keelline.toml` is a fixed name, which that guard exempts so that a person may keep it out of
git. Every refusal of the write that can be known in advance — a name, a gate already
enforcing, nothing left to promote, a document the editor cannot rewrite, a manifest the
re-stamp cannot read — comes before the first gate runs, because a custom gate is a command and
running it is not free. What is left is the disk refusing the write itself.

**What prints.** Gate names, which the loader holds to a grammar, counts and fixed text; never a
plan's path or text.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from keelline.assess.gates import GateContext, run_gates
from keelline.config.layout import is_adoption_plan
from keelline.config.loader import read_document
from keelline.config.owned import OwnedKeyError, Value, rewrite
from keelline.config.schema import CONFIG_CHECK, Config
from keelline.docs.api import lint
from keelline.errors import Failure, Refusal
from keelline.project.api import rewrite_owned
from keelline.scaffold import Manifest

NOT_AN_ADOPTION_PLAN = (
    "the adoption plan must be a markdown file directly under [paths] plans, with keelline as "
    "a word of its name"
)
PLAN_FAILS = "the adoption plan has {count} finding(s) under `keelline plan check`; fix them first"
NOT_A_GATE = "every name must be a configured gate, and config is the configuration check"
NAMED_ENFORCES = (
    "a gate named already enforces; name only gates that do not, or none for every gate left"
)
ALL_ENFORCE = "every configured gate already enforces; there is nothing left to promote"
UNEDITABLE = (
    "[keelline] state or enforced is written in a shape Keelline does not rewrite in place, so no "
    "gate ran and nothing was written; write each on one line as it stands now, `state = {state}` "
    "and `enforced = {enforced}`, and run the command again"
)


@dataclass(frozen=True)
class Transition:
    before: str
    after: str
    promoted: tuple[str, ...] = ()
    failing: dict[str, int] = field(default_factory=dict)  # ran and did not pass: its count
    unanswered: tuple[str, ...] = ()  # could not run


def begin(root: Path, config: Config, plan: Path) -> Transition:
    """Check `plan` as an adoption plan and mark an `initialised` project `adopting`.

    Past `initialised` the state is kept and nothing is written: a project may carry any number
    of adoption plans, and nothing records which one began it.
    """
    root = root.resolve()
    resolved = plan.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise Refusal(NOT_AN_ADOPTION_PLAN)
    if not is_adoption_plan(config, resolved.relative_to(root).as_posix()):
        raise Refusal(NOT_AN_ADOPTION_PLAN)
    findings = lint(root, config, plans=[resolved]).findings
    if findings:
        raise Failure(PLAN_FAILS.format(count=len(findings)))
    state = config.keelline.state
    if state != "initialised":
        return Transition(state, state)
    rewrite_owned(root, {("keelline", "state"): "adopting"})
    return Transition(state, "adopting")


def _refuse_an_uneditable_document(root: Path, config: Config) -> None:
    """Refuse, before any gate runs, a document whose `state` or `enforced` the editor cannot
    rewrite in place.

    A trial edit of both keys, discarded. The values differ from any the document can hold, so
    the editor meets both lines rather than skipping one already at its value: `config` is never
    a gate's name, and the loader refuses it in `enforced`. Those values are made up, so the
    editor's own refusal, which tells the person to write the value it was setting, is not
    passed on: following it would enforce what no gate earned, or write a list that does not
    load. The remedy names the values the document holds now, in the one-line shape the editor
    rewrites. Both are bounded: a member of the lifecycle and gate names the loader has held to
    a grammar, each written as a plain basic string.
    """
    text = read_document(root)
    if text is None:
        return  # the configuration was loaded from it a moment ago; the write refuses its absence
    state = config.keelline.state
    other = "installed" if state != "installed" else "adopting"
    try:
        rewrite(text, {("keelline", "state"): other, ("keelline", "enforced"): (CONFIG_CHECK,)})
    except OwnedKeyError:
        listed = ", ".join(f'"{name}"' for name in config.keelline.enforced)
        raise OwnedKeyError(UNEDITABLE.format(state=f'"{state}"', enforced=f"[{listed}]")) from None


def promote(root: Path, config: Config, names: Sequence[str], *, base: str) -> Transition:
    """Enforce the named gates if every one of them passes now, or, with none named, each
    configured gate not yet enforcing that passes; `base` is what `plan` and `commit` judge a
    range against."""
    configured = config.gate_names
    if any(name not in configured for name in names):
        raise Refusal(NOT_A_GATE)
    enforcing = config.keelline.enforcing
    if any(name in enforcing for name in names):
        raise Refusal(NAMED_ENFORCES)
    state = config.keelline.state
    wanted = [n for n in configured if n in (names or configured) and n not in enforcing]
    if not wanted:
        if state == "installed":
            raise Refusal(ALL_ENFORCE)
        # Every configured gate enforces and the state never said so: complete it.
        rewrite_owned(root, {("keelline", "state"): "installed", ("keelline", "enforced"): ()})
        return Transition(state, "installed")
    _refuse_an_uneditable_document(root, config)  # trial rewrite; before any gate runs
    Manifest.read(root)  # the write re-stamps its record, so one it cannot read refuses here
    results = run_gates(GateContext(root, config, base), wanted)
    failing = {r.name: len(r.findings) for r in results if r.answered and r.failing}
    unanswered = tuple(r.name for r in results if not r.answered)
    promoted = tuple(r.name for r in results if not r.failing)
    if (names and (failing or unanswered)) or not promoted:
        return Transition(state, state, (), failing, unanswered)
    enforced = enforcing | set(promoted)
    installed = enforced >= set(configured)
    after = "installed" if installed else "adopting"
    listed: Value = () if installed else tuple(n for n in configured if n in enforced)
    rewrite_owned(root, {("keelline", "state"): after, ("keelline", "enforced"): listed})
    return Transition(state, after, promoted, failing, unanswered)
