"""`doctor`: what an installation looks like from the outside (§8.4).

This area **reports and never repairs.** Every other area in this package writes something;
this one reads.

**It runs several subprocesses, and every one of them only asks.** The count used to be given
here as "exactly two" and that was wrong: besides Keelline's own hook wrapper with `--version`
and `git ls-remote --exit-code` against the remote `[ci] ref` names, `pre-commit` asks
`guards.api.hooks_dir` where the overlay keeps its hooks, `attached` reaches `read_binding`,
which asks `git` for `origin`, and resolving the note store in overlay mode asks again — four
launches on the green end-to-end fixture, measured. What is true of all of them is the part
that matters: none writes, and exactly one, the `ci-ref` row, leaves this machine, and only
when a `[ci] ref` is set at all.

**Two of them read something the environment named, and neither trusts it.** `wrapper`
executes only the plugin root this process derived from its own module path, because a root a
variable named is a script a repository can choose (`checks.plugin_root`); `diagnostics` reads
the sink's log through `${CLAUDE_PLUGIN_DATA}` and prints a count and not one byte of it,
because nothing here can establish who wrote that file (`checks._diagnostics`).

A check that cannot be answered says `skip` and names what a measurement would need — three of
the fifteen do on a healthy installation — because a check that returned green because it could
not look would be strictly worse than one that admits it.
"""
