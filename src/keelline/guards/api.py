"""The import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for the same measured reason `keelline.memory.api`
gives: `keelline.hooks.registry` imports `keelline.guards.hooks`, which imports the package
first, so a re-export list in `__init__.py` would pull this whole area into every `discover()`
call and reddens `tests/test_areas.py`. Keeping the surface one level down costs a consumer six
characters and keeps discovery cheap.

Everything a consumer lane needs is re-exported here, and the list is chosen from what those
lanes actually reach for: `hooks-core` needs nothing to import — its handlers are discovered —
but reads `LEAK_REASON` and `SLEEP_REASON` in its smoke assertions; `setup` needs `install`,
`uninstall`, `Installed`, `Removed` and `HOOK_NAME` to offer and undo the git hook; `attach` and
`doctor` need `hooks_dir` alone, to ask where an overlay's hooks really live rather than assume
`.git/hooks` — an overlay with `core.hooksPath` set, or one that is a worktree or a submodule,
keeps them somewhere else, and both lanes had the same wrong spelling hardcoded; `assess`
needs the commit rules (`offending_lines`, `check_range`, `Report`, `Violation`, `Offence`,
`ATTRIBUTION_LABELS`), the hygiene and audit surface (`inspect`, `Hygiene`, `contained_roots`,
`Finding`, `SHAPES`, `import_roots`, `scan_paths`, `suite_files`) and the scanner any later
guard is built on (`Heredoc`, `tokenize`, `segments`, `operator_pieces`, `command_words`); and
the judge itself (`judge`, `Verdict`, `ALLOW`). A lane that needs something absent from this
list grows it deliberately, in a commit that says which lane and why.
"""

from keelline.guards.attribute import VERDICTS, Attribution, attribute
from keelline.guards.audit import SHAPES, Finding, import_roots, scan_paths, suite_files
from keelline.guards.bashscan import (
    Heredoc,
    command_words,
    operator_pieces,
    segments,
    tokenize,
)
from keelline.guards.bgcleanup import ALLOW, LEAK_REASON, RESTORE_HINT, SLEEP_REASON, Verdict, judge
from keelline.guards.commit import (
    ATTRIBUTION_LABELS,
    Offence,
    Report,
    Violation,
    check_range,
    offending_lines,
    strip_message,
)
from keelline.guards.githooks import (
    HOOK_MARKER,
    HOOK_NAME,
    Installed,
    Removed,
    hooks_dir,
    install,
    uninstall,
)
from keelline.guards.hygiene import Hygiene, inspect, red_exit
from keelline.guards.roots import contained_roots

__all__ = [
    "ALLOW",
    "ATTRIBUTION_LABELS",
    "HOOK_MARKER",
    "HOOK_NAME",
    "LEAK_REASON",
    "RESTORE_HINT",
    "SHAPES",
    "SLEEP_REASON",
    "VERDICTS",
    "Attribution",
    "Finding",
    "Heredoc",
    "Hygiene",
    "Installed",
    "Offence",
    "Removed",
    "Report",
    "Verdict",
    "Violation",
    "attribute",
    "check_range",
    "command_words",
    "contained_roots",
    "hooks_dir",
    "import_roots",
    "inspect",
    "install",
    "judge",
    "offending_lines",
    "operator_pieces",
    "red_exit",
    "scan_paths",
    "segments",
    "strip_message",
    "suite_files",
    "tokenize",
    "uninstall",
]
