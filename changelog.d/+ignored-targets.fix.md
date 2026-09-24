`keelline init`, `upgrade` and `uninstall` no longer write, overwrite or remove an existing
file git ignores at a place a `[paths]` value chose. Such a value pointing an artifact at a
git-ignored `.env`, say, let Keelline's section land in it with nothing in the diff to show for
it; now the run is refused before anything is written, dry run included, naming the file and
saying to point the key elsewhere or take it out. A new file, a fixed name such as `CLAUDE.md`
or `keelline.toml`, a preset's own place, a tracked file that happens to match an ignore
pattern and the files `[artifacts] local` keeps out of git are not affected, so a `CLAUDE.md`
in your global excludes works as before; outside a git repository nothing changes.
