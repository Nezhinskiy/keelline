Your project's CI can now call Keelline's gates as one reusable workflow, pinned at a commit
sha. A `uses:` line in your own workflow file runs `keelline gate` against your checkout in one
`gates` job, with no resolver and no build backend, in two steps: the configuration check and
the built-in gates first, then your own gates from `[gates.custom]`, only once the first step
passed, so no command your repository wrote runs where the verdict is decided. Both start Python
as `python3 -P -s`, so neither a module in the checkout nor a `.pth` file in a user site
directory loads in their process. Within a step every gate runs whatever the one before it said,
so fixing findings does not cost a round trip each, except a custom gate, which does not start
once the run has failed; a custom gate runs on the runner image with nothing of your project
installed, so it installs its own toolchain.

The base is resolved once to a commit from `refs/remotes/origin/<base>`, so a tag named like the
branch cannot stand in for it; on a pull request a `base:` input that disagrees with the base the
platform reports is refused rather than preferred, and a project root reached through a symbolic
link is refused. The new `only` input runs a chosen few, for a caller that wants one check row
per gate from a matrix of its own; the configuration check runs whatever it names. What the tree
under review cannot do is turn off the gates it is about to face; what your `.github/` still
needs is the ordinary protection, because the `uses:` line and its `with:` block live in a file
a pull request can edit. The Keelline that runs is the commit your `uses:` line pins, read off
the platform's own record of which reusable workflow is executing and asserted against `git
rev-parse HEAD` before a gate runs, so a ref that resolved to something else fails the run
instead of quietly checking out a default branch.

Keelline now proves its own install the way you would: a smoke workflow installs this plugin
from the checkout with the real harness CLI under a temporary configuration directory on
Linux and macOS, feeds every `hooks/hooks.json` entry the event it is filed under through the
*installed* wrapper, runs `doctor` over the result, calls the reusable workflow against a
committed fixture project, and runs the clone-to-exfiltration scenario — on every change and
once a week, because the harness moves underneath the plugin and only a run can say whether
an install still works. A companion workflow, dispatched by hand, exercises the two moving
`owner/repo/…@ref` call forms, so that the two forms the documentation does not recommend are
still known to work.
