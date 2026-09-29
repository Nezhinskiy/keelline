`stayfixed overlay create --template` and `stayfixed setup --overlay create:<owner>/<name>` now
generate the overlay from your own `<owner>/stayfixed-overlay-template` when you have published
one, and from `github.com/stayfixed/stayfixed-overlay-template` otherwise, so an account that
never ran `stayfixed overlay publish-template` can still create an overlay from GitHub. The
fallback is named with its host, so a `gh` pointed at a GitHub Enterprise host (`GH_HOST`) never
generates your overlay from whoever owns the `stayfixed` account there. The command names the
template it used. A failure to find out whether you have your own (an expired token, a network
error, no `gh` on the machine) stops with `gh`'s own message and creates nothing, instead of
falling back. `stayfixed overlay publish-template` is unchanged.
