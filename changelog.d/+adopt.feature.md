`keelline adopt begin PLAN` starts a project's adoption with a plan that passes
`plan check`, and `keelline adopt promote [GATE…]` enforces gates once they pass: every gate
that passes now when none is named, or the named ones together. When every configured gate
enforces, the project is `installed`.
`begin` refuses a plan whose row in the roadmap's trail declares no state, which a first listing
would otherwise record as delivered, and tells a missing plan apart from a misnamed one. When a
gate stays advisory, `promote` ends by saying where its findings are, and says when the base
`plan` and `commit` compare against is not in the checkout. A custom gate that leaves
`keelline.toml` unparseable during a promotion is reported as invalid TOML, with its position.
