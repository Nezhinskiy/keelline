The reusable workflow takes a `timeout-minutes` input: the job's time limit, 15 by default and
anywhere from 5 to 60. A project whose own gates need longer than 15 minutes raises it with one
line under its caller's `with:`, and keeps those gates under the reusable workflow's protection
rather than moving them into a workflow of its own. A value outside the range, or one that is not
a whole number, fails the job in its first step, and a job that runs out of time is cancelled,
which a required check never counts as a pass.
