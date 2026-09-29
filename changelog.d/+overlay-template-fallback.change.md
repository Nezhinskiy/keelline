`stayfixed overlay create --template` and `stayfixed setup --overlay create:<owner>/<name>` now
generate the overlay from `github.com/stayfixed/stayfixed-overlay-template` when you have not
published your own `<owner>/stayfixed-overlay-template`, so an account that never ran
`stayfixed overlay publish-template` can still create one; the fallback is looked up on
github.com whatever host `gh` defaults to. The command names the template it used. When `gh`
cannot say whether you have your own (an expired token, a network error, no `gh` on the
machine), it stops with `gh`'s own message and creates nothing, instead of falling back.
