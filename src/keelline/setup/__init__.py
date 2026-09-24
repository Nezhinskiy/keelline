"""Configure a machine for Keelline, and a repository's own commit-message hook.

An area, discovered by name: `commands.py` gives it the `setup` command and `api.py` is what
another lane may import. `setup` is the only writer of the machine configuration file — the
file `config.loader._personal` and `memory.store.overlay_root` already read. Its schema is
`setup`'s, and neither of those readers changes.
"""
