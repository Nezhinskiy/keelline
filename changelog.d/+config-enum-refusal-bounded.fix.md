A `keelline.toml` whose `[keelline] state`, `[memory] mode` or `[ci] mode` is not one of the
values Keelline knows is now refused without the value being quoted back. All three are strings
a repository author chooses, bounded by no grammar, and the refusal is relayed to a model by the
`init` and `attach` skills — so `; got '…'` put unbounded repository bytes into it, escaped but
neither bounded in content nor in length.

The line still names the key and the values it may take, which are Keelline's own vocabulary and
the whole of what a reader needs to fix the file they already have open. This is the same ruling
the `[project] name` refusal and the unknown-key messages in that loader already took.
