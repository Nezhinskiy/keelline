A `[paths]` value inside Keelline's own `.keelline/` directory, at any depth and in any case, is
now refused when `keelline.toml` loads, naming the key and never the value, the way one inside
`.git` already was. `.keelline/local/` holds state git never sees, such as attach's ledger and the
local-only memory notes, and a committed `[paths] agents_md` pointing into it had `keelline
upgrade` write the `AGENTS.md` section into that file, where no checkout could restore it.
