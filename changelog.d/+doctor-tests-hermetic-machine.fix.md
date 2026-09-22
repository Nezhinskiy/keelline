`doctor`'s own test helper now defaults its machine-configuration path into the test's temporary
directory. It defaulted to `None`, which the code under test resolves as
`~/.config/keelline/config.toml` — the real one — so on a developer machine that had run
`keelline setup --overlay`, thirty-four cases read that developer's actual overlay and note
store while believing they were hermetic. No shipped behaviour changes; the suite does.
