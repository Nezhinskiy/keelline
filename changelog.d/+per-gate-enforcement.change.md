`stayfixed.toml` gains `[gates]`, the gates a project runs: the five built-in gates by
default, and argv commands of its own under `[gates.custom.<name>]`. It also gains
`[stayfixed] enforced`, the gates promoted while adopting, which `stayfixed adopt promote`
writes. An `installed` document whose `enforced` lists only some of the gates is refused.
