A `keelline.toml` that is a symbolic link is now refused by every command that reads it, before
anything is read through it. `keelline gate`, `assess` and `init` already refused one; `adopt`,
`bugs check`, `plan check`, `docs check` and the other commands followed it, so a repository
whose `keelline.toml` pointed at `/dev/zero` kept them reading until the machine ran out of
memory.
Whatever the link points at, the answer is the same: `keelline hook` refuses a `PreToolUse` call
and lets every other event through, naming the rule rather than reporting an internal error;
`keelline doctor` reports a `keelline.toml` that does not load; and `keelline init --questions`
refuses instead of asking its questions over a link to `/dev/zero`.
