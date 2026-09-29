When a real `stayfixed.toml` does not load (a file or value the loader refuses, or a `[paths]`
entry that leaves the project or passes through a symlink, such as a symlinked `AGENTS.md`),
`stayfixed hook` now says so in its own words and points at `stayfixed docs check` for the
detail, instead of printing `internal error` with the loader's message. The verdict per event is
unchanged: a `PreToolUse` call is still refused, and every other event still continues open.
