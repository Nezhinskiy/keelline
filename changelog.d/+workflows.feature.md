Your project's CI can now call Keelline's gates as one reusable workflow, pinned at a commit
sha. A `uses:` line in your own workflow file runs `keelline gate` against your checkout, in one
job, with no resolver and no build backend. Every gate runs whatever the one before it said, so
fixing findings does not cost a round trip each.

What the gates judge you by is read from your base branch, never from the branch under review.
The workflow resolves the base branch to one commit and reads its `keelline.toml`, and your
tree's copy may tighten it — enforce more gates, add a gate, lower a budget — but not loosen it:
a change the rule does not admit is refused while the base enforces any gate. Each gate is then
advisory or enforcing on its own, as that configuration says: an advisory gate's findings are
warning annotations and the job stays green, and an enforcing gate's failure fails the job. On a
pull request a `base:` input that disagrees with the base the platform reports is refused rather
than preferred. What the tree under review cannot do is turn off the gates it is about to face;
what your `.github/` still needs is the ordinary protection, because the `uses:` line and its
`with:` block live in a file a pull request can edit. While the base carries no `keelline.toml`
at all (which is every project's first pull request), your tree's copy decides. The Keelline
that runs is the commit your `uses:` line pins, read off the platform's own record of which
reusable workflow is executing and asserted against `git rev-parse HEAD` before a gate runs, so
a ref that resolved to something else fails the run instead of quietly checking out a default
branch.

Keelline now proves its own install the way you would: a smoke workflow installs this plugin
from the checkout with the real harness CLI under a temporary configuration directory on
Linux and macOS, feeds every `hooks/hooks.json` entry the event it is filed under through the
*installed* wrapper, runs `doctor` over the result, calls the reusable workflow against a
committed fixture project, and runs the clone-to-exfiltration scenario — on every change and
once a week, because the harness moves underneath the plugin and only a run can say whether
an install still works. A companion workflow, dispatched by hand, exercises the two moving
`owner/repo/…@ref` call forms, so that the two forms the documentation does not recommend are
still known to work.
