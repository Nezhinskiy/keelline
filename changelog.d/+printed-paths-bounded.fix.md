Keelline no longer prints a file name taken from the repository exactly as it found it. The
repository chooses its own file names, and a tracked file could be named with a line break
followed by `::error::…`, which a GitHub Actions runner reads from a job's output as a workflow
command, or with a terminal escape sequence. Printed as is, either one reached CI or the
reader's terminal as an instruction rather than as a name. This affected the findings of
`keelline bugs check`, `keelline docs check`, `keelline plan check` and `keelline memory refs`,
the lists printed by `keelline docs trail`, `keelline bugs renumber` and `keelline memory index`,
and the refusals that name a bug entry, a plan or a note that could not be read.

A path made only of letters, digits, `.`, `_` and `-`, in segments separated by `/`, still
prints as itself, so ordinary output is unchanged. On a summary line, any other path prints as
`<unprintable name; see --json>`, and the `--json` output carries the full name, escaped. A
refusal has no `--json` payload to point to, so there the name is quoted with its line breaks
and control characters escaped. The same applies to a `docs/trail.toml` `[states]` key that
names no document.

Three values from the repository that are not file names get the same escaping where a refusal
names them: a `memory.groups` entry that `keelline memory refs` could not resolve, the
`[project] base_branch` that `keelline test attribute` compares against when no `--base` is given,
and the error text for an invalid `docs/trail.toml` theme pattern, which repeats characters from
the pattern itself.
