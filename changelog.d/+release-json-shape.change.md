`keelline release check` and `keelline release hashes --check` report drift the way every other
command does.

Both used to raise instead of returning, so under `--json` a run that found drift printed
`{"error": "failed", "summary": "failed: ..."}` and nothing else — the machine-readable object
changed *shape* on exactly the condition a consumer runs these commands to detect, and the
`versions` map a clean run offered was absent from the run that mattered. Both objects now
carry `summary`, `problems` and (`versions` or `files`) in either outcome.

The exit codes are unchanged (`0`, and `1` on drift). What moved is the line itself: it is
printed on stdout without the `keelline: failed: ` prefix, as every other command's findings
are. A version source this gate cannot parse at all is still a failure, not a finding.
