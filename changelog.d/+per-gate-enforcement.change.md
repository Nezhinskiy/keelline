`keelline.toml` gains `[gates]`, the gates a project runs: the five built-in gates by
default, any of which it may drop, and argv commands of its own under
`[gates.custom.<name>]`. It also gains `[keelline] enforced`, the gates promoted while
adopting. `state = "installed"` still means every gate the project runs enforces, and an
`installed` document whose `enforced` lists only some of them is now refused.
