An overlay whose `keelline.requires` carries an absurdly long version no longer costs a session
every line it was about to hear. `satisfies` promises `None` for a declaration it cannot read,
but its version grammar bounded no component, and CPython refuses to convert an integer string
past 4300 digits — so a floor like `>=999…9.0.0`, which no repository can write but an owner can
mistype into the overlay's own manifest, raised instead. `keelline doctor` reported it as "this
check could not run", and the `SessionStart` handler's backstop swallowed the exception together
with every other line of the same result: a session was told nothing at all, not even that the
repository is not attached to the overlay it is reading.

Each component is now bounded at nine digits, and to ASCII digits. A floor written in another
numbering system — `\d` matches every Unicode decimal digit, and `int()` converts them — used to
validate, compare, and print back verbatim into a session line and a `doctor` row; it is now
reported as a form this Keelline does not read, which is what it is.
