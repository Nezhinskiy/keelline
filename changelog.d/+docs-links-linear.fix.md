`keelline docs check` and the `docs` gate read a document's links in linear time. A document
of repeated unclosed links, `[a](` over and over, made the link reader quadratic: a fifth of a
megabyte took close to a minute, in the step that judges a pull request and in `keelline assess`.
