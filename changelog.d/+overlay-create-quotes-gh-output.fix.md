`stayfixed overlay create` and `stayfixed overlay init` now quote what `gh`, `git` and
`pre-commit` print in their failure lines the way stayfixed quotes a name a repository chose: a line
break or an escape sequence in it is escaped, so it can neither start a CI workflow command such as
`::error::` nor drive a terminal, and an answer longer than 120 characters is cut to its first 120
and its length.
