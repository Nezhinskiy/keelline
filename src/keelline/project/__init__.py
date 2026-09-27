"""The `project` area: the shipped project footprint, and `keelline init`.

Deliberately empty of imports. Area discovery imports a package before it imports the
submodule it wants, so a re-export list here would pull this area — and with it the
configuration layer, the scaffold engine and four other areas' surfaces — into every
`discover()` call. `api.py` is the import surface; `tests/test_surfaces.py` asserts this file
imports nothing at all.
"""
