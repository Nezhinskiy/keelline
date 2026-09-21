A session in a repository that keeps its notes in a private overlay now hears, once at its
start, what stands between it and those notes: that the repository is not attached, that the
overlay recorded a different remote, that a note directory is still a real directory `attach`
would have to move, that the overlay requires a newer Keelline, or — when nothing else is
wrong — that the overlay holds commits or changes the other machine cannot see yet. Each is
a fixed sentence naming the command to run; a bound, linked, up-to-date repository hears
nothing. The lines come from the plugin: the overlay's own `hooks/hooks.json` stays empty,
and what the owner keeps in `common/claude/hooks.json` still reaches a repository only
through `keelline attach`.

`keelline doctor` grows a sixteenth row, `overlay-requires`, which reads the Keelline floor an
overlay declares and goes red when the Keelline running does not meet it; and its `ci-ref`
row now judges `[ci] ref` as what the configuration asks for — the commit of a released
tag — reports the `v1` alias as the mutable opt-in it is, and checks that the rendered
workflow pins the same ref. The value no longer reaches `git` at all.
