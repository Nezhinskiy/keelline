A `keelline.toml`, a machine configuration file, or an overlay's own `projects/<name>/project.toml`
that will not parse is now reported as the file and the position the parser stopped at — `line 4,
column 12` — and nothing else the parser had to say. Python's TOML reader puts the offending text
into its own message for several kinds of fault: a duplicate table is reported with the table's
name in it, and a TOML key can be any quoted text at all. So the old messages could hand a
document's own bytes back to you, or to an agent relaying them, as part of a sentence that looked
like Keelline's. The position is all four readers print now: `keelline init` adopting a document
it did not write, the two configuration loaders, and `keelline attach` reading the overlay's
binding record.
