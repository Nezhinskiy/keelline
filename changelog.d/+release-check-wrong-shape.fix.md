`keelline release check` names the file when a version source parses but has the wrong shape: a
`plugin.json` or `marketplace.json` whose top level is not an object, a `pyproject.toml` whose
`project` is not a table, or a marketplace `plugins` value that is not a list of objects. Each
ended the command as an internal error naming no file, and a marketplace entry written as a
string was passed over; a `marketplace.json` that is not JSON at all is now reported as such.
