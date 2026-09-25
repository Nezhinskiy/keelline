The reusable workflow runs `keelline gate` in its one `gates` job, in two steps: the
configuration check and the built-in gates first, then the project's own gates from
`[gates.custom]`, only once the first step passed, so no command the repository wrote runs
where the verdict is decided. Each gate is advisory or enforcing as the base's `keelline.toml`
says. The base is resolved once to a commit from `refs/remotes/origin/<base>`, so a tag named
like the branch cannot stand in for it, and a project root reached through a symbolic link is
refused. A custom gate runs on the runner image with nothing of the project installed, so it
installs its own toolchain. The new `only` input runs a chosen few, for a caller that wants
one check row per gate from a matrix of its own; the configuration check runs whatever it
names.
