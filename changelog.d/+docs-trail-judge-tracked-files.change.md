The `docs` and `trail` gates judge tracked files, because CI checks out nothing else. When a file
one of them reads — `AGENTS.md` or a file its links name, the roadmap or its `trail.toml` — is
on disk but not tracked by git, `keelline assess` now reports that gate as unable to judge the
tree as CI will, with an `untracked` item naming the files, and `keelline adopt promote` no
longer enforces it: it would fail every pull request in CI, where the file is absent. A tracked
symlink on the way to such a file, a symlinked directory included, is followed to what it names,
which must be tracked and inside the repository too, since a checkout leaves the link dangling
otherwise. The refusal says to commit
the file (an ignored one needs its ignore rule removed, or `git add -f`), or to keep it out of
git and take the gate out of `[gates] builtin`. `keelline gate` itself is unchanged.
