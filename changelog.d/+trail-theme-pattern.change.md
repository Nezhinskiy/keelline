A `trail.toml` theme's `pattern` is now a small part of regular-expression syntax — literal text,
`.`, `.*`, `|`, `^` and `$`, and `\` before punctuation — matched without backtracking. A
repository's pattern such as `(a+)+$` used to make `keelline docs trail`, the `trail` gate and
`keelline assess` run for as long as the machine let them on one ordinary file name. The shipped
`.*` and patterns like `widget` or `gadget|gizmo` mean what they meant; a pattern using any other
syntax is refused, naming the theme and the syntax that is allowed.
