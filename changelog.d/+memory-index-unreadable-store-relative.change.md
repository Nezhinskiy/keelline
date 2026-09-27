`keelline memory index --json` now lists the notes it could not read under `unreadable` by their
path inside the memory store, such as `developer/broken.md`, rather than by their absolute path.
Its summary line already named them that way, and `keelline memory refs` names them that way in
both, so one command no longer gives two answers about one file. A consumer that joined these
entries onto a directory joins them onto the store's directory instead.
