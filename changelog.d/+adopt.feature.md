`keelline adopt begin PLAN` starts a project's adoption with a plan that passes
`plan check`, and `keelline adopt promote [GATE…]` enforces gates once they pass: every gate
that passes now when none is named, or the named ones together. When every configured gate
enforces, the project is `installed`. A custom gate is promoted only once the base branch has
its command, since that is when `keelline gate` starts running it; until then it is not run and
is named as not on the base.
`keelline adopt promote --builtin` runs the built-in gates and none of the commands
`[gates.custom]` names, so a clone whose commands you have not agreed to run can still be
adopted: its custom gates are named as not run and stay advisory. The `init` skill uses it when
you decline to run them.
`begin` refuses a plan whose row in the roadmap's trail declares no state, which a first listing
would otherwise record as delivered, and tells a missing plan apart from a misnamed one. When a
gate stays advisory, `promote` ends by saying where its findings are, and says when the base
`plan` and `commit` compare against is not in the checkout. A custom gate that leaves
`keelline.toml` unparseable during a promotion is reported as invalid TOML, with its position.
