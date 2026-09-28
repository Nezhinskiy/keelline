A file stayfixed reads as UTF-8 that is not UTF-8 — `stayfixed.toml`, the machine configuration,
the trust record, a harness settings file, the attach ledger, a `.gitignore`, an overlay's
records and manifests, the release sources — is now reported as that file's failure, naming it,
instead of ending the command in an internal error. So is a `stayfixed.toml` that cannot be
read at all, such as a directory at its path.
