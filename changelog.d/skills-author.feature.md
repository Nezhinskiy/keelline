`keelline test attribute --command CMD` attributes one failing command to the change or to
the environment: it runs the command three times — the working tree as it is, `HEAD`'s
committed tree and the merge-base with the base branch, each extracted with `git archive`
into a scratch directory — and prints the verdict the three exit codes determine. The
working tree is read once and never written, and the command carries its own environment
sync, which is what makes the tool the same for every stack.
