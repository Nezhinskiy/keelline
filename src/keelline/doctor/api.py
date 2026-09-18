"""The doctor area's import surface: everything another lane may import from it.

`assess` (wave 5) will gate on this report, and the command module in this area is its first
consumer. A lane that needs something absent from this list grows it deliberately, in a commit
that says which lane and why — it does not import a private module of this area.

`plugin_root` was on this list and is not any more: nothing outside this area imports it, and
the one test that reads it takes it from `keelline.doctor.checks`, which is its own area's
module and nobody else's business. The status vocabulary stays whole — `OK`, `WARN`, `RED`,
`SKIP` and the `STATUSES` they belong to — for the reason `attach/api.py` gives about
`Binding.state`: half a closed vocabulary cannot be read by the consumer that gets a value
from it.
"""

from keelline.doctor.checks import (
    OK,
    RED,
    SETTINGS_FILES,
    SKIP,
    STATUSES,
    WARN,
    Check,
    run_checks,
)

__all__ = [
    "OK",
    "RED",
    "SETTINGS_FILES",
    "SKIP",
    "STATUSES",
    "WARN",
    "Check",
    "run_checks",
]
