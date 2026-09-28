`stayfixed init` on a repository whose hand-written `stayfixed.toml` holds a key that is not a
plain name (letters, digits, `_` and `-`) now refuses naming only the table the key sits in.
It used to quote the key itself back, control characters included, before the configuration
was validated.
