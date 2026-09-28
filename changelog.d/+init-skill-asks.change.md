The `init` skill now asks what `stayfixed init --questions` lets a person answer — the project's
name, base branch, agents and profile as one confirmation, then where the notes live and which
files stay out of git — through the harness's own ask tool where it has one and within that
tool's limits, or one plain question per turn where it has none. It shows the dry run of the
answered `stayfixed init --yes`, writes only on an explicit yes, and then starts the adoption:
`stayfixed assess`, an adoption design and plan with an up-to-date trail, and `stayfixed adopt
begin` on a second explicit yes. Silence, a timeout or an empty answer is never a yes.
