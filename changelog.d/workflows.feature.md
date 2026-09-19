Your project's CI can now call Keelline's gates as one reusable workflow, pinned at a commit
sha. A `uses:` line in your own workflow file runs `docs check`, `bugs check`, `plan check`,
`commit check` and `docs trail --check` against your checkout, with no resolver and no build
backend. Every gate runs whatever the one before it said, so fixing findings does not cost a
round trip each.

What the gate judges you by is read from your base branch, never from the branch under
review. The state comes from `keelline.toml` as the base ref carries it, and once that state
is `installed` your tree's copy must match the base's byte for byte on every other branch or
the run fails before a gate runs — a pull request cannot turn off the gates it is about to
face. While the base says `initialised` or `adopting`, or carries no `keelline.toml` at all
(which is every project's first pull request), that same difference is a warning, every gate
still runs, and every failure is one warning annotation instead of a red job; once the base
says `installed`, a failed gate fails the job. The Keelline that runs is the commit your
`uses:` line pins, read off the platform's own record of which reusable workflow is executing
and asserted against `git rev-parse HEAD` before a gate runs, so a ref that resolved to
something else fails the run instead of quietly checking out a default branch.

Keelline now proves its own install the way you would: a smoke workflow installs this plugin
from the checkout with the real harness CLI under a temporary configuration directory on
Linux and macOS, feeds every `hooks/hooks.json` entry the event it is filed under through the
*installed* wrapper, runs `doctor` over the result, calls the reusable workflow against a
committed fixture project, and runs the clone-to-exfiltration scenario — on every change and
once a week, because the harness moves underneath the plugin and only a run can say whether
an install still works. A companion workflow, dispatched by hand, exercises the two moving
`owner/repo/…@ref` call forms, so that the two forms the documentation does not recommend are
still known to work.
