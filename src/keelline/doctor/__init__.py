"""`doctor`: what an installation looks like from the outside (§8.4).

This area **reports and never repairs.** Every other area in this package writes something;
this one reads.

**It runs several subprocesses, and every one of them only asks.** The count used to be given
here as "exactly two" and that was wrong: besides Keelline's own hook wrapper with `--version`
and `git ls-remote --exit-code` over the public repository's tags, which is how `[ci] ref` is
judged, `pre-commit` asks
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

A check that cannot be answered says `skip` and names what a measurement would need, because a
check that returned green because it could not look would be strictly worse than one that admits
it. **Three is the floor and not the count**, and `doctor/commands.py` has the whole of it:
three checks cannot be answered by this build at all, five more skip on a state of the machine,
and `run_checks` skips fifteen at once when `keelline.toml` is missing or will not load. The
third of those is easy to meet by hand — `diagnostics` skips whenever no harness data root is
set, which is every `keelline doctor` run from a terminal rather than from a hook.
"""
