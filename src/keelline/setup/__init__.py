"""Configure a machine for Keelline, and a repository's own commit-message hook (§5.2, §8.1).

An area, discovered by name: `commands.py` gives it the `setup` command and `api.py` is what
another lane may import. `setup` is the only writer of the machine configuration file — the
file `config.loader._personal` and `memory.store.overlay_root` already read, and neither of
those readers changes for this plan (DP5).
"""
