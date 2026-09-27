A summary line that lists names now names at most eight of them and says how many more there are,
as every other command's summary line already did. `keelline docs trail` printed every document
that entered the trail with no declared state, and `keelline memory index` every note it could not
read and every note or `memory.index_extra` pointer it held back, however many there were; `--json`
still carries every name. Two refusals with no `--json` are bounded the same way. The one for
`docs/trail.toml` `[states]` keys that name no document now counts every stale key, names the
first eight in sorted order, and says that a re-run after updating those names the rest. The one
for a memory store none of whose `memory.groups` resolves now counts the groups and gives the
reasons for the first eight. And a `[states]` key or a `[[theme]]` label longer than 120
characters is named in a refusal by its first 120 characters and its length, where one key of
200 000 characters used to make a line of 200 000 characters.
