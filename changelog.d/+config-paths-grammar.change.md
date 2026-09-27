`keelline.toml`'s `[paths]` table is now held to a plain-path grammar, and two of the loader's
refusals no longer echo back the value that triggered them.

A `[paths]` value has to look like a relative path — letters, digits, `.`, `_`, `-` and `/`,
starting with one of those and never a symlink-shaped byte — before it is accepted at all. A
`keelline.toml` that loaded yesterday with a `[paths]` value outside that shape (a multi-line
string, a value carrying characters a path never needs) is refused today, naming which key and,
in words, the rule it must match. `project.name`'s own refusal, and this new one, both stop quoting
the value back into the message: either only names the key and the rule, never what was
written.

`project.name` is also anchored strictly now. Its grammar ended in `$`, which in Python matches
before a trailing newline, so a multi-line `name = """widget\n"""` loaded and became a path
segment carrying a newline; it ends in `\Z`, and that spelling is refused.
