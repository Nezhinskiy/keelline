A TOML file nested a few thousand levels deep — `keelline.toml`, the machine configuration, a
roadmap's `trail.toml`, an overlay's project record, `pyproject.toml` or `uv.lock` — is now
reported as a file that does not parse, naming it, instead of ending the command with an
internal error. Under `keelline gate` and `keelline assess` such a `trail.toml` makes the `trail`
gate one that could not run, and every other gate still answers. `keelline release check` reports
a `plugin.json` nested past `json`'s depth the same way, as JSON that does not parse.
