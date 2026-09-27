`docs trail` and its `--check` no longer list a gitignored document in the roadmap when git gives
no answer about the repository. Inside a git work tree, a git that could not be run, ran past its
time limit or refused the checkout (for example as one of dubious ownership) used to read as
"nothing is ignored" and "nothing is untracked", so every document on disk was listed — a
local-only one included — in a file that is committed. The command now fails (exit 1), names
the question git did not answer, and writes nothing. Outside a repository every document is
still listed.
