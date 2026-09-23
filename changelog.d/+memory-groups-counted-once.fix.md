A `memory.groups` entry written twice is now one group. The list was taken from `keelline.toml`
as-is, and it is the one repository-authored list Keelline reports back as a count you are asked
to act on — so `groups = ["developer", "developer"]` made `keelline attach` refuse naming two
groups that had not moved into the overlay, `keelline attach --check` print
`real_directories: 2`, and the session line tell the model two, all about one directory whose
remedy was already done. Entries are kept once, in the order your document wrote them.

The refusal for an entry that is not a group also says what it means. Since a configured path's
components started being read exactly as written, an entry of `""` or `"."` — both of which name
the notes directory itself rather than a group in it — and one with a trailing or doubled slash are
refused along with one that escapes; all four used to be told their entry "does not stay inside
this project's paths.memory", which is false of every one of them. The line now says the entry
does not name a subdirectory of `paths.memory`, which is true of all of them, and it still never
quotes the entry back.
