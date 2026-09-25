`keelline.toml` gains `[gates]`, the gates a project means to run: the five built-in gates
by default, and argv commands of its own under `[gates.custom.<name>]`. It also gains
`[keelline] enforced`, the gates promoted while adopting. Both are accepted and validated when
the file loads, and the gate that honours them ships later: until it does, the reusable
workflow runs every built-in check and fails a pull request only once the base's `state` is
`installed`. An `installed` document whose `enforced` lists only some of the gates is refused.
