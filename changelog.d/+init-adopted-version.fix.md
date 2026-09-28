`stayfixed init` on a repository whose hand-written `stayfixed.toml` has no `[stayfixed] version`
writes that one key into it. Before writing anything, it refuses a hand-written file the next
command could not load: one with no `[project] name`, or one whose `state` and `enforced` the
loader holds apart. It used to finish, and leave a repository no command could read.
