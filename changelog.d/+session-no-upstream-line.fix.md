A session is no longer told that an overlay with no upstream has "0 unpushed commit(s)". A branch
with no upstream has *every* commit unpushed — the count is unknown, not zero — and the two lines
were appended independently, so the state produced "the overlay's branch has no upstream, so
nothing backs it up" immediately followed by a count of zero, with the number on the sentence
that was false.

The no-upstream line now carries the count that is knowable there, the uncommitted changes, and
tells you to push the branch with `-u`; the unpushed-commits line is reached only when there is a
real number to print. The documented budget for that handler is also corrected: its two extra
`git` calls fall on the *healthy* path, not the other way round, and because the once-per-session
marker is banked only when the handler actually says something, a repository with nothing to
report is asked again on every resume rather than once per session.
