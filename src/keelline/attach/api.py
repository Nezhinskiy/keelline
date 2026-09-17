"""The attach area's import surface: everything another lane may import from it.

`doctor` (Wave E) reports on what this lane wrote and needs the binding, the diff and the
ledger by name; `setup` runs `attach --check` and reads the same `Result`. A lane that needs
something absent from this list grows it deliberately, in a commit that says which lane and
why — it does not import a private module of this area.
"""

from keelline.attach.binding import BOUND, MISMATCH, STATES, UNBOUND, Binding, read_binding
from keelline.attach.permissions import (
    LOCAL_SETTINGS,
    PermissionDiff,
    check,
    diff_permissions,
    overlay_entries,
)
from keelline.attach.write import LEDGER, Attached, AttachLedger, attach, ledger

__all__ = [
    "BOUND",
    "LEDGER",
    "LOCAL_SETTINGS",
    "MISMATCH",
    "STATES",
    "UNBOUND",
    "AttachLedger",
    "Attached",
    "Binding",
    "PermissionDiff",
    "attach",
    "check",
    "diff_permissions",
    "ledger",
    "overlay_entries",
    "read_binding",
]
