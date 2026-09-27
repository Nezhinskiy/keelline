The reusable workflow takes a `timeout-minutes` input: the job's time limit, 15 by default and any
whole number of minutes from 5 to 60. A project whose own gates need longer than 15 minutes raises
it with one line under its caller's `with:`, and keeps those gates under the reusable workflow's
protection rather than moving them into a workflow of its own. Any other value fails the job in its
first step; a job that runs out of time is cancelled, which a required check never counts as a
pass. The input bounds this one job: a pull request that edits the rest of the caller file, adding
a matrix or pointing `uses:` elsewhere, changes `.github/`, which code-owner review governs when it
merges.
