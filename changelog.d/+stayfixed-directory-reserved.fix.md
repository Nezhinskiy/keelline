A `[paths]` value inside stayfixed's own `.stayfixed/` directory, at any depth and in any case, is
now refused when `stayfixed.toml` loads, naming the key and never the value, the way one inside
`.git` already was. `.stayfixed/local/` holds state git never sees, such as attach's ledger and the
local-only memory notes, so a committed `[paths]` value pointing into it could have a command
write a project file there, over something no checkout could restore.
