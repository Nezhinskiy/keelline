"""Bind a repository to the machine owner's private overlay, and unbind it again (§6.3).

An area, discovered by name: `commands.py` gives it the `attach` and `detach` groups and
`api.py` is what another lane may import. It writes nothing a repository chose — the overlay
root comes from the machine file, the store is that overlay's own directory for this project,
and a write that would widen a permission refuses without an explicit confirmation.
"""
