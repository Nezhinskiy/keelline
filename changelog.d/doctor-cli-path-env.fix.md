`keelline doctor`'s `cli-path` row now resolves `keelline` against the `PATH` it was handed
rather than against the process environment directly. Nothing changes for an ordinary `keelline
doctor` run, which is handed its own environment; what changes is that a caller passing an
environment — a hook, a harness, a test — gets an answer about that environment instead of about
the shell the command happened to start in.
