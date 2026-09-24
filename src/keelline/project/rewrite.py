"""`rewrite_owned`: the one way a command changes a tool-owned key in `keelline.toml`.

Three steps, each owned elsewhere. `config.owned.rewrite` edits the text and proves the edit by
parsing it back. `fsops.write_within` writes it. And the `config` record in
`.keelline/manifest.json` is re-stamped when it described the file before the edit, so a document
nobody but Keelline has touched stays one `keelline uninstall` recognises, and an edited one is
never blessed.

**The record is re-stamped before the document is written.** An interruption between the two
leaves a record naming the new bytes beside a file still holding the old ones. The next run
computes the same new bytes, finds the record already naming them, and writes the file. In the
other order the interruption leaves the new file beside a record naming the old bytes; the next
run finds nothing to rewrite, and `uninstall` keeps an untouched `keelline.toml` for good.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import keelline
from keelline.config.loader import CONFIG_FILE, read_document
from keelline.config.owned import Value, rewrite
from keelline.errors import Refusal
from keelline.fsops import UnsafePath, write_within
from keelline.scaffold import Manifest, digest

NO_DOCUMENT = f"{CONFIG_FILE} is not there, so there is no tool-owned key to rewrite"
CONFIG_RECORD = "config"


def rewrite_owned(root: Path, changes: Mapping[tuple[str, str], Value]) -> None:
    text = read_document(root)
    if text is None:
        raise Refusal(NO_DOCUMENT)
    document = rewrite(text, changes)
    if document == text:
        return
    manifest = Manifest.read(root)
    record = manifest.get(CONFIG_RECORD)
    if record is not None and record.sha256 == digest(text):
        stamped = replace(record, sha256=digest(document), version=keelline.__version__)
        manifest.with_record(stamped).write(root)
    try:
        write_within(root, CONFIG_FILE, document)
    except (UnsafePath, OSError) as exc:
        raise Refusal(f"{CONFIG_FILE} cannot be written: {exc}") from exc
