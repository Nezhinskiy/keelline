The session-start overlay line no longer re-runs its two `git` calls when the same session asks
again. `overlay-status` speaks at most once per session, and the marker that enforces that is
banked only when the handler had something to say — so a bound, linked, pushed, satisfied
repository returns silence, banks nothing, and is asked again on every `startup`, `resume`,
`clear`, `compact` and `fork`. It is that healthy repository which pays for the `git`: the
overlay's `git status` and `git rev-list` are reached only when nothing above them found anything
wrong, and together with the binding's own `origin` query that is nine seconds against a
ten-second budget shared with the handler that links the note store.

Those last two calls are now gated on the event's own `source`. On a `compact` — the running
conversation continuing, under the session id the marker is filed under — they are skipped, so a
healthy repository costs five seconds there instead of nine. `startup`, `resume`, `fork`, `clear`
and a payload carrying no `source` all still pay: a resume is a new launch, often days later, over
an overlay the conversation may have left dirty, and an invocation that cannot be placed in a
context is treated as a new one rather than as one already answered.

The cost, which is the reason this is a change and not only a speed-up: an overlay that becomes
unpushed *during* a session whose start found nothing to say is not reported at that session's
compactions. `keelline doctor` answers on demand, and the next resume or start says it too.
