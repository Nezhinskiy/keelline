`keelline init`, `upgrade` and `uninstall` no longer write, overwrite or remove a file git
ignores. A `[paths]` value pointing an artifact at such a file (a git-ignored `.env`, say) let
Keelline's section land in it with nothing in the diff to show for it; now the run is refused
before anything is written, dry run included, and the refusal counts the files without naming
them. A tracked file that happens to match an ignore pattern is not affected, nor are the files
`[artifacts] local` keeps out of git, and outside a git repository nothing changes.
