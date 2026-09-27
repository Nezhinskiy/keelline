Keelline no longer prints a name taken from the repository exactly as it found it. A repository
chooses its own file names, note names and `memory.groups` entries, and any of them could hold a
line break followed by `::error::…`, which a GitHub Actions runner reads from a job's output as a
workflow command, or a terminal escape sequence. Printed as is, either one reached CI or the
reader's terminal as an instruction rather than as a name. This affected:

- the findings of `keelline bugs check`, `keelline docs check`, `keelline plan check` and
  `keelline memory refs`;
- the lists printed by `keelline docs trail`, `keelline bugs renumber` and `keelline memory index`;
- the refusals that name a bug entry, a plan or a note that could not be read, a symlink found on
  the way to a configured path, a `docs/trail.toml` `[states]` key that names no document, and a
  `memory.groups` entry that could not be resolved.

A name made only of ASCII letters, digits, `.`, `_` and `-`, in segments separated by `/`, still
prints as itself, so ordinary output is unchanged. Any other name — including an ordinary one
with a space or a non-ASCII letter — is handled one of two ways:

- **On a summary line**, it prints as `<unprintable name; see --json>`, and the `--json` output
  carries the full name, escaped. In `keelline assess`, whose own `--json` and inventory file
  hold the finding, it prints as `<a name outside the path grammar>` instead.
- **In a refusal**, which has no `--json` to point to, it is quoted with its line breaks and
  control characters escaped, so the name still arrives whole.

When some `memory.groups` entries could not be resolved, the refusal's first line now gives their
number only, and each name appears in the reasons below it, inside the region marked as the
repository's data. `keelline memory index` now names a note it cannot read by its path inside the
store rather than by its absolute path.
