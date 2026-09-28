A refusal of `[project] name`, of a custom gate's name, of `stayfixed init --name` or of the name
`init` would detect now states the rule in words — one lowercase path segment of letters, digits,
`.`, `_` and `-`, led by a letter or digit — instead of printing a regular expression whose
Python-only `\Z` anchor reads as a literal `Z` everywhere else.
