A `keelline.toml` that is a symbolic link is now refused by every command that reads it, before
anything is read through it. `keelline gate`, `assess` and `init` already refused one; `adopt`,
`bugs check`, `plan check`, `docs check` and the other commands followed it, so a repository
whose `keelline.toml` pointed at `/dev/zero` kept them reading until the machine ran out of
memory.
