"""The attach area's import surface: everything another lane may import from it.

The list is chosen from what consumers outside this area actually reach for, and every name on
it carries the reason beside it — a surface that survives a trim with no explanation is what
made the trim necessary. A lane that needs something absent from this list grows it
deliberately, in a commit that says which lane and why — it does not import a private module of
this area.

`doctor` is the one consuming area, and it is the whole of what any module outside this area
imports from here:

- the ledger (`ledger`, `LEDGER`) and `AttachLedger`, because `ledger` returns it: a return
  type absent from this list is a value `doctor` can hold and cannot declare, and
  `tests/test_surfaces.py` derives that rule rather than restating it;
- the binding (`read_binding`, `Binding`, `MISMATCH`), and `BOUND`, `UNBOUND` and `STATES` with
  them. `Binding.state` is one of `STATES` and `doctor` already branches on `MISMATCH`;
  publishing one member of a closed vocabulary and hiding the other two leaves a consumer able
  to recognise the bad state and unable to name the good ones. The set is the export, not the
  member that happened to have a caller first;
- the overlay's granted hook entries (`overlay_entries`, `LOCAL_SETTINGS`, the file they live
  in). `overlay_entries` names `Binding` in its signature too.

**`setup` is not a consumer.** This docstring used to say "`setup` runs `attach --check` and
reads the same `Result`"; `src/keelline/setup/` imports nothing from `keelline.attach`, and
`attach --check` is this area's own command module calling its own `permissions.check`. The
permission-diff half of the area — `check`, `diff_permissions` and the `PermissionDiff` it
returns — was published on the strength of that sentence and left when the sentence did.

**Trimmed, in the wave-4 surface trim: `attach`, `detach`, `Attached` and `Detached`.** They
were published against a second sentence of the same kind — "`tests/test_install_path.py`, the
walkthrough that runs the four packages in the order a person does, is the other consumer, and
it drives `attach` and `detach`, whose returns are `Attached` and `Detached`". That walkthrough
drives the argument parser: `step("attach", "--store", ..., "--yes", ...)`, which is the point
of it, because the commands' argv wiring is what it exists to exercise. It imports two surfaces,
`keelline.doctor.api` and `keelline.memory.api`, and reaches no name on this list. The two verbs
are this area's own command module's, and their results are read where they are returned.

The claim is the same shape as the one this docstring corrected two paragraphs up, and as the
one `setup/api.py` corrected about its own `setup` and `SetupReport` — three of them now, all
naming a test that runs a command rather than a module that imports a name. A published surface
argued from prose is a surface nobody measured: the wave-4 pass counted `src/`, `scripts/` and
`tests/` and never read the sentence, and the sentence is what kept the names.
"""

from keelline.attach.binding import BOUND, MISMATCH, STATES, UNBOUND, Binding, read_binding
from keelline.attach.permissions import LOCAL_SETTINGS, overlay_entries
from keelline.attach.write import LEDGER, AttachLedger, ledger

__all__ = [
    "BOUND",
    "LEDGER",
    "LOCAL_SETTINGS",
    "MISMATCH",
    "STATES",
    "UNBOUND",
    "AttachLedger",
    "Binding",
    "ledger",
    "overlay_entries",
    "read_binding",
]
