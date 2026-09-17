"""The setup area's import surface: everything another lane may import from it.

`doctor` (Wave E) checks what `setup` installed and needs the machine reader and `USER_SETTINGS`
by name. A lane that needs something absent from this list grows it deliberately, in a commit
that says which lane and why — it does not import a private module of this area.
"""

from keelline.setup.machine import USER_SETTINGS, Written, read_machine, write_machine
from keelline.setup.run import SetupReport, setup

__all__ = [
    "USER_SETTINGS",
    "SetupReport",
    "Written",
    "read_machine",
    "setup",
    "write_machine",
]
