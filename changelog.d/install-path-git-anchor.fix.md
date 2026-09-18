The hook wrapper's refusal to run an interpreter from inside your checkout is now measured
against two anchors rather than one, and the `git` it asks for the second is no longer chosen by
`PATH`.

The containment compared a candidate interpreter against `CLAUDE_PROJECT_DIR` — which reaches a
hook from a committed `.claude/settings.json` `env` block, the same channel the containment
exists to close. A repository that set `PATH` to its own tree *and* named a project root outside
that tree therefore had its own `python3` measured as "outside the project root", on exactly the
machines the rule exists for: those where none of the built-in absolute candidates answers, such
as a `pyenv`, `nix` or `asdf` installation. The wrapper now takes both `CLAUDE_PROJECT_DIR` and
`git`'s answer and refuses a candidate inside either, so both anchors have to move at once.

`git` itself was resolved through `PATH`. On the Codex path, where `CLAUDE_PROJECT_DIR` is unset
and `git` is the only anchor there is, a repository that committed a `git` and named its own tree
on `PATH` had that binary executed on every hook invocation, before any Keelline guard ran, and
its output became the project root every hook then worked against. The wrapper now runs the first
`git` it finds at a fixed list of absolute paths, asking your own installs before `/usr/bin/git`,
and nothing under `$HOME` is on that list. If you have no `git` at any of them you will see a new
`KL_NO_GIT` token — a degradation under `open` policy, a refusal under `closed` — rather than a
containment that keeps its shape and loses its strength. Keelline's own `git` calls are
unchanged and still resolve through `PATH`, so the `git` you installed is the one that answers
everywhere else.

Two smaller repairs beside them. `KL_NO_PY` now says which of its two states it is in: an
interpreter that was found inside your checkout and skipped names the remedy where you are
standing, instead of printing the same sentence as "nothing answered at all". And the wrapper's
change into the project root no longer consults `CDPATH`, which could both write a directory name
to a hook's stdout ahead of Keelline's own output and land the hook in a different tree, and it
accepts a project directory whose name begins with `-`.

`keelline doctor` no longer reports a `[ci] ref` red for containing `::` when that `::` is part
of a legal IPv6 address — `ssh://user@[2001:db8::1]/repo.git` is a remote URL, not a transport
helper. The check now follows git's own parse and still refuses `ext::…` and every other real
`<helper>::<address>` spelling.
