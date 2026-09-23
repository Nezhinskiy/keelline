`keelline doctor` no longer tells a machine that moved its overlay that it never recorded one.
The `pre-commit` and `overlay-requires` rows both began with "no overlay root is recorded on this
machine" whenever the recorded root was not a directory — false for a machine that recorded one
and then reorganised its directories, and with an empty remedy under it, which the doctor skill
tells the model not to read as a finding. The two states are now two rows with two sentences: the
machine that has not run `keelline setup` still gets the old line and no remedy, because there is
nothing wrong with it; the machine whose recorded overlay is not there is told so and handed the
command that fixes it. Both rows read the sentences from one place, so neither can drift from the
other. `cli-path`'s remedy also names the repository through the same constant every other row
uses rather than spelling the address a second time.
