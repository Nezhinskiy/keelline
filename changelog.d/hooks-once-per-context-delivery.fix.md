A hook handler that runs once per context no longer spends its single delivery on a run
that delivered nothing. The dispatcher used to mark the handler's key after every
successful run, so the first unrelated tool call of a session consumed a notice meant for
the first failing test run, and the notice was never shown at all. The key is now marked
only when the handler actually delivered — a context the harness received, or a deny —
and only after the checks that can reject the result have passed.
