A summary line that lists names now names at most eight of them and says how many more there are,
as every other command's summary line already did. `keelline docs trail` printed every document
that entered the trail with no declared state, and `keelline memory index` every note it could not
read and every note or `memory.index_extra` pointer it held back, however many there were; `--json`
still carries every name. The refusal for `docs/trail.toml` `[states]` keys that name no document,
which has no `--json`, now counts every stale key, names the first eight in sorted order, and says
that a re-run after updating those names the rest.
