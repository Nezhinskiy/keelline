"""The attach area's import surface: everything another lane may import from it.

The list is chosen from what consumers outside this area actually reach for, and every name on
it is either one of those or argued below. A lane that needs something absent from this list
grows it deliberately, in a commit that says which lane and why — it does not import a private
module of this area.

`doctor` is the one consuming area: it reads the ledger (`ledger`, `LEDGER`, `AttachLedger`),
the binding (`read_binding`, `Binding`, `MISMATCH`) and the overlay's granted hook entries
(`overlay_entries`, `LOCAL_SETTINGS`). `tests/test_install_path.py` — the walkthrough that runs
the four packages in the order a person does — is the other, and it drives `attach` and
`detach`, whose returns are `Attached` and `Detached`.

Three names are here with no importer at all, on purpose:

- `BOUND`, `UNBOUND` and `STATES`. `Binding.state` is one of `STATES`, and `doctor` already
  branches on `MISMATCH`; publishing one member of a closed vocabulary and hiding the other two
  leaves a consumer able to recognise the bad state and unable to name the good ones. The set is
  the export, not the member that happened to have a caller first.
- `AttachLedger`, because `ledger` is exported and returns it: a return type absent from this
  list is a value `doctor` can hold and cannot declare. `tests/attach/test_surface.py` derives
  that rule rather than restating it.

**`setup` is not a consumer.** This docstring used to say "`setup` runs `attach --check` and
reads the same `Result`"; `src/keelline/setup/` imports nothing from `keelline.attach`, and
`attach --check` is this area's own command module calling its own `permissions.check`. The
permission-diff half of the area — `check`, `diff_permissions` and the `PermissionDiff` it
returns — was published on the strength of that sentence and left when the sentence did.
"""

from keelline.attach.binding import BOUND, MISMATCH, STATES, UNBOUND, Binding, read_binding
from keelline.attach.permissions import LOCAL_SETTINGS, overlay_entries
from keelline.attach.write import (
    LEDGER,
    Attached,
    AttachLedger,
    Detached,
    attach,
    detach,
    ledger,
)

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
    "Detached",
    "attach",
    "detach",
    "ledger",
    "overlay_entries",
    "read_binding",
]
