`keelline gate` is the gate a pull request faces, runnable locally. It reads the base's
`keelline.toml` at an exact commit and at the project's own path, admits only changes that
tighten, runs the configuration check and every configured gate (built-in or the project's own)
advisory or enforcing as the verdict says, and prints the verdict the reusable workflow acts on.
`--builtin` runs no command from `keelline.toml`, and `--custom` runs only those.

What a pull request may change is judged key by key over what the loader derives, never by byte:
it may enforce more gates and move its state forward, add a gate, drop or re-command one the base
does not enforce, and lower a budget; the preset's name, the profile, the harnesses and the
project's name are free; an upgrade moves the recorded version to exactly the running Keelline and
the workflow pin only to a released commit. Any other change is refused while the base enforces
any gate, and lands by a direct push to the base branch. A refused change runs under the base's
configuration, and a gate either side enforces enforces.

Both copies of `keelline.toml` are read as UTF-8, whatever the locale: a base copy that is not
UTF-8 text fails the run (exit 1) in the words the tree's own copy fails in, and is never
parsed. A base copy that does not load fails the run too, and the message names the base's copy,
which only a direct push to the base branch can fix; it is never read as the base having none.

A run that fails with a gate failing ends by saying where the findings are, and a project root
given with a `..` component is refused in words that say so.
