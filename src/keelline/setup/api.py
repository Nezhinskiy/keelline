"""The setup area's import surface: everything another lane may import from it.

`doctor` checks what `setup` installed and needs `USER_SETTINGS` by name — that is the whole of
what another area imports from here. `tests/test_install_path.py`, the walkthrough that runs the
four packages in the order a person does, drives `setup` itself, and `SetupReport` comes with it
because a return type absent from this list is a value that caller can hold and cannot declare.

A lane that needs something absent from this list grows it deliberately, in a commit that says
which lane and why — it does not import a private module of this area.

**Trimmed, in the wave-3 boundary remediation.** This docstring used to claim `doctor` "needs
the machine reader and `USER_SETTINGS` by name"; `doctor` imports `USER_SETTINGS` alone, so
`read_machine` and `write_machine` left with the claim, and `Written` — `write_machine`'s
result, discarded at both of its call sites — left with them.
"""

from keelline.setup.machine import USER_SETTINGS
from keelline.setup.run import SetupReport, setup

__all__ = [
    "USER_SETTINGS",
    "SetupReport",
    "setup",
]
