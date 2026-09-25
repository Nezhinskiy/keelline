"""The import surface: everything a consumer lane may import from this area.

A module and not the package's `__init__`, for the same measured reason `keelline.memory.api`
gives: `keelline.hooks.registry` imports `keelline.guards.hooks`, which imports the package
first, so a re-export list in `__init__.py` would pull this whole area into every `discover()`
call and reddens `tests/test_areas.py`. Keeping the surface one level down costs a consumer six
characters and keeps discovery cheap.

The list is what consumers outside this area actually reach for: the git hook, one shared rule
and one gate:

- `setup` offers and undoes the git hook (`install`, `uninstall`, `HOOK_NAME`), and `Installed`
  and `Removed` come with the two verbs, because a return type absent from this list is a value
  `setup` can hold and cannot declare.
- `attach`, `doctor` and `setup`'s own tests ask where an overlay's hooks really live rather
  than assume `.git/hooks` (`hooks_dir`, `HOOK_MARKER`) — an overlay with `core.hooksPath` set,
  or one that is a worktree or a submodule, keeps them somewhere else, and both lanes had the
  same wrong spelling hardcoded.
- `ledger.scan` and `memory.refs` both ask which roots a configuration's paths may reach
  (`contained_roots`), and two spellings of that would be two answers.
- `assess` runs the `commit` gate (`commit_gate`), `(root, config, base) -> list[Finding]`;
  `commit check` reads the same range through the same `check_range`.

A lane that needs something absent from this list grows it deliberately, in a commit that says
which lane and why.

**Trimmed, in the first half of the wave-3 refactor pass.** Twenty-nine names went, and every
one of them was published against `assess`, which did not exist then: the commit rules
(`offending_lines`, `check_range`, `strip_message`, `Report`, `Violation`, `Offence`,
`ATTRIBUTION_LABELS`), the hygiene and audit surface (`inspect`, `Hygiene`, `red_exit`,
`Finding`, `SHAPES`, `import_roots`, `scan_paths`, `suite_files`), the scanner any later guard
would be built on (`Heredoc`, `tokenize`, `segments`, `operator_pieces`, `command_words`), the
failure attribution (`attribute`, `Attribution`, `VERDICTS`) and the background-cleanup judge
(`judge`, `Verdict`, `ALLOW`, `LEAK_REASON`, `SLEEP_REASON`, `RESTORE_HINT`, the last three
against "hooks-core's smoke assertions", which import none of them). Each is still where it was
written and is reachable by its own module; what went is the claim that another area reads it.
`overlay/api.py` made the same ruling about a template tree published against "the release lane
will need it": that lane grows the list when it arrives, which is what this docstring asks of
every other lane. When `keelline assess` arrived it needed one name, `commit_gate`, and none of
the twenty-nine.
"""

from keelline.guards.commit import commit_gate
from keelline.guards.githooks import (
    HOOK_MARKER,
    HOOK_NAME,
    Installed,
    Removed,
    hooks_dir,
    install,
    uninstall,
)
from keelline.guards.roots import contained_roots

__all__ = [
    "HOOK_MARKER",
    "HOOK_NAME",
    "Installed",
    "Removed",
    "commit_gate",
    "contained_roots",
    "hooks_dir",
    "install",
    "uninstall",
]
