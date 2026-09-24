## Keelline

This repository is initialised with Keelline. `keelline.toml` names its document paths and
its note store. `%%BUG_INDEX%%` is a generated index over `%%BUGS%%/` — never edit it by hand;
`keelline bugs index` renders it. `%%ROADMAP%%` carries the design-and-plan trail between its
markers, which `keelline docs trail` rewrites; specs live under `%%SPECS%%/` and plans under
`%%PLANS%%/`. Gates run advisory until `[keelline] state` in `keelline.toml` is `installed`.%%PROFILE%%
