A `keelline.toml` whose `[keelline] preset` or `[keelline] profile` Keelline cannot use is now
refused without the value being quoted back. Both are strings a repository author chooses. The
refusal for a name outside the allowed characters is reached exactly when the value is
malformed, so it could carry escape sequences and line breaks into a terminal, and into a model
through the skills that relay refusals.

Each refusal now names the key, states the rule in words, and lists the presets or profiles
this version ships. `keelline setup --preset` gives the same refusal, naming `--preset` rather
than a file.
