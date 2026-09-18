"""Which overlay this repository is bound to, and whether the binding is really this one's.

**DP3, and two of its three rules live here.** The overlay is trusted *by construction*, and
the construction is that `config.machine.machine_config_path(interactive=False)` makes the
machine file unselectable by a repository — that module spends twenty lines on why gating one
of a pair of equivalent variables "is not a partial defence, it is a redirect with a longer
name". So:

1. the overlay root comes from `overlay_root(machine)` and never from `--store`. Deriving it
   from the store's own parent would make the source of every allow rule and every hook entry
   `attach` merges a path on a command line — in a harness where command lines are written by a
   model that has read the repository; and
2. `--store` must be exactly `<overlay>/projects/<name>/memory`, which is what
   `permitted_roots(overlay, name)` already calls this project's own share. A store elsewhere
   under the overlay would attach and then fail on every session start, because `memory.store`
   holds every linked group to those same two roots — so `attach` would have produced a store
   the hook path refuses, which is the worst of both.

The third rule is a write and lives in `write.py`.

**The two remotes on a `Binding` are repository-authored bytes**, by the Global Constraints'
own list, and nothing here puts either into a summary, a `Result.data` or a refusal message.
What this module computes *about* them — one of three state labels — is Keelline's own and may
be printed.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from keelline.config.loader import load
from keelline.errors import Failure, Refusal
from keelline.memory.api import (
    PROJECT_RECORD,
    PROJECTS,
    origin_remote,
    overlay_root,
    permitted_roots,
)

UNBOUND = "unbound"
BOUND = "bound"
MISMATCH = "mismatch"
STATES = (UNBOUND, BOUND, MISMATCH)
# The one directory under `projects/<name>/` that holds notes; `permitted_roots` is what names
# it, and this constant exists only so `write.py` can build the rest of the record's path from
# a store it was handed.
STORE_DIR = "memory"


@dataclass(frozen=True)
class Binding:
    """What the overlay records about this repository, and what this repository says it is.

    `remote` is this checkout's `origin` and `recorded` is what the overlay wrote down for
    `project`; both are repository-authored and neither is safe to print. `state` is this
    module's own answer and is.
    """

    project: str
    overlay: Path
    store: Path
    remote: str | None
    recorded: str | None
    state: str


def _record(overlay: Path, project: str) -> Path:
    return overlay / PROJECTS / project / PROJECT_RECORD


def _recorded(overlay: Path, project: str) -> str | None:
    """The remote the overlay bound to this project, or `None` when it has bound none.

    A record that exists and cannot be read raises rather than answering `None`.
    `memory.store._bound` answers False for the same file, which is right for the hook path —
    it degrades closed and says "run `keelline attach`". Here that advice *is* the command, and
    "no record" is the state that invites a rebind, so a broken record has to stop the run
    instead of quietly becoming a first attach.
    """
    record = _record(overlay, project)
    if not record.is_file():
        return None
    try:
        raw = tomllib.loads(record.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Failure(f"{record} cannot be read: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise Failure(f"{record} is not valid TOML: {exc}") from exc
    value = raw.get("remote")
    return value if isinstance(value, str) and value else None


def _state(recorded: str | None, origin: str | None) -> str:
    """`unbound`, `bound` or `mismatch` — and never `bound` because nobody looked.

    §12's hostile-clone row turns on this comparison: "attach compares the remote to the
    overlay's record and refuses". The clone chooses `project.name`; it does not choose which
    remote the overlay recorded under that name.
    """
    if recorded is None:
        return UNBOUND
    if recorded != origin:
        return MISMATCH
    return BOUND


def read_binding(root: Path, *, store: Path, machine: Path | None) -> Binding:
    """The binding this repository would attach under, or a refusal that it may not.

    `project.name` arrives through `config.loader.load` and never out of the raw TOML, because
    that loader is what holds it to one path segment (§7.4 names `../common` as the value it is
    protecting against, and the name becomes a directory under the overlay's `projects/`).
    """
    config = load(root, machine=machine)
    project = config.project.name
    overlay = overlay_root(machine)
    if overlay is None:
        raise Refusal(
            "no overlay root is recorded in the machine configuration, so there is nothing to "
            "bind this repository to; run `keelline setup` first"
        )
    expected = permitted_roots(overlay, project)[1]
    if store.resolve() != expected.resolve():
        raise Refusal(
            f"--store must name this project's own directory inside the overlay this machine "
            f"records ({expected}), and {store} is not it. The overlay root comes from the "
            f"machine configuration and never from an argument"
        )
    recorded = _recorded(overlay, project)
    origin = origin_remote(root)
    return Binding(project, overlay, store, origin, recorded, _state(recorded, origin))
