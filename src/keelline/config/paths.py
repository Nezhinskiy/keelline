"""Root containment for the `[paths]` fields, and for nothing else yet (§7.4).

`validate_paths` iterates `config.paths.as_dict()`, so the guard covers exactly the fields of
`schema.Paths` and no others. Four path-shaped, repository-writable fields never reach
`contained()`: `ledger.code_roots`, `artifacts.local`, `memory.groups` and
`memory.index_extra`. A `keelline.toml` setting
`ledger.code_roots = ["../../../../etc", "/etc/passwd"]` loads without a murmur, while the same
strings under `[paths]` are refused. Until that changes, the ledger and memory lanes must call
`contained()` themselves on the fields they consume; widening the guard here would change
`Config`'s shape, so it belongs with the lane that first reads those fields.

Two rules, not one: `PATH_VALUE` is the grammar half — what a value must match before it may be
printed anywhere, a report included — and `contained()` is the root half, deciding whether the
value may be written *here*. The same four unguarded fields above are unguarded by both.

**The component rule is `fsops`', and this module borrows it rather than restating it.**
`contained()` used to split the value with `Path(relative).parts`, which normalises an empty
component, a trailing slash and a leading `./` out of existence; `fsops` splits the raw string
and refuses all three. So `plan()` found nothing wrong with `docs//roadmap-history.md` and
`apply()` raised on it after ten artifacts and the manifest were already written, leaving a
repository `init` would not touch again. The two spellings agreed for four review rounds, which
is what a duplicated rule does until it does not.
`checked_components` is the single spelling now; the import goes subpackage-to-leaf, so `fsops`
stays the leaf the hook path depends on it being.
"""

from __future__ import annotations

from pathlib import Path

from keelline.config.schema import PATH_VALUE, Config
from keelline.errors import Refusal
from keelline.fsops import (
    UnsafePath,
    checked_components,
    names_component,
    names_control_directory,
)


class PathEscape(Refusal):
    """A configured path that leaves the project root or passes through a symlink."""


def contained(
    root: Path,
    relative: str,
    *,
    allow_final_symlink: bool = False,
    resolved_root: Path | None = None,
) -> Path:
    try:
        # The empty path, an absolute path, `..`, `.` and an empty segment, all read off the
        # caller's own spelling — one rule, in `fsops`, so a value this function accepts is a
        # value the write can reach. `fsops` raises `UnsafePath`, an `OSError`, because a leaf
        # module owns no user-facing verdict; a configured path's verdict is a `Refusal`, and
        # the translation is all this line adds.
        parts = checked_components(relative)
    except UnsafePath as exc:
        raise PathEscape(str(exc)) from exc
    # Git's control directory is refused by the call above, at every depth and in any case, and
    # this is where that matters for a *configured* path: `contained()` is the function every
    # `[paths]` value and every lane-supplied path goes through, above the first write.
    # `validate_paths` asks the same question one key at a time so its refusal can name the key;
    # the rule itself is `fsops.names_control_directory` in both places, because a guard stated
    # twice is the defect this module was just repaired for.
    target = root.joinpath(*parts)
    for ancestor in [target, *target.parents]:
        if ancestor == root:
            break
        if ancestor.is_symlink() and not (allow_final_symlink and ancestor == target):
            raise PathEscape(f"{relative!r} passes through a symlink at {ancestor}")
    # Defence in depth. The guards above refuse every escape a path string can express — the
    # empty path, an absolute path, any `..` component, and a symlink at any level between the
    # root and the target — so the comparison below is the net under them rather than the
    # guard itself. It is here for the path form nobody has anticipated; a caller validating
    # many paths against one root passes `resolved_root` so this resolve happens once.
    if resolved_root is None:
        resolved_root = root.resolve()
    resolved = target.parent.resolve() / target.name if allow_final_symlink else target.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise PathEscape(f"{relative!r} resolves outside the project root")
    return target


# Keelline's own directory in a project: the manifest, `.keelline/local/` (attach's ledger, the
# local-only note store, `[artifacts] local` artifacts) and the assessment. Spelled here, beside
# the loop that reserves it, because `config` imports no area and the scaffold engine, `attach`
# and `memory` all import `config`; `tests/config/test_paths.py` holds each of their paths to lie
# under it, so the two spellings cannot drift apart.
KEELLINE_DIRECTORY = ".keelline"


def names_keelline_directory(relative: str) -> bool:
    """Whether any component of `relative` is Keelline's own directory, spelled in any case.

    `fsops.names_component`, the test `fsops.names_control_directory` asks too, and for the same
    two reasons. Any depth:
    a package inside a monorepo initialised on its own keeps its own `.keelline/local/`, and a
    parent project's `[paths]` value must not reach that either. Any case: the default
    filesystems on macOS and Windows fold case, so `.Keelline/local/attach.json` is the same
    file.
    """
    return names_component(relative, KEELLINE_DIRECTORY)


# `PATH_VALUE` in words, for the refusal a person reads. Kept beside the one reader that prints
# it; a change to the grammar is a change to this sentence.
PATH_RULE = (
    "segments of letters, digits, `.`, `_` and `-` joined by single `/`, none of them `.` or "
    "`..`, the first not starting with `-`, and no `/` at either end"
)


def validate_paths(config: Config, root: Path) -> dict[str, Path]:
    resolved_root = root.resolve()
    for name, relative in config.paths.as_dict().items():
        if not PATH_VALUE.match(relative):
            # Named and never quoted: this is the value a report would otherwise print.
            # The rule in words, not `PATH_VALUE.pattern`: the lookahead that closes `.` and `..`
            # as segments is correct and is no sentence a person can act on.
            raise PathEscape(f"paths.{name} is not a plain relative path: {PATH_RULE}")
        if names_control_directory(relative):
            # Named and never quoted, for the same reason. Nothing reserved git's control
            # directory: the grammar admits a leading dot, and `contained()` refused an
            # absolute path, `..` and a symlink but not a directory. So a clone could set
            # `agents_md = ".git/hooks/pre-commit"` — a `MANAGED_REGION`, exempt from the
            # engine's "exists and Keelline did not write it" guard — and have its own
            # executable pre-commit hook rewritten in place, mode and all.
            #
            # The anchor is the project root the CLI resolved, and `.git` is git's own name
            # inside it; the clone authors this value and nothing else, so it cannot move the
            # directory being reserved. `.git` and not "a leading dot", because
            # `.github/workflows/` is Keelline's own footprint.
            raise PathEscape(
                f"paths.{name} names git's control directory, which is git's and not "
                "Keelline's to write into"
            )
        if names_keelline_directory(relative):
            # Named and never quoted. `.keelline/` is where Keelline keeps its manifest and, under
            # `.keelline/local/`, state git never sees: attach's ledger and the local-only notes.
            # A `[paths]` value is committed, and `agents-md` is a `MANAGED_REGION` inserted into
            # whatever file `agents_md` names, exempt from the "exists and Keelline did not write
            # it" guard — so a pulled commit setting `agents_md = ".keelline/local/attach.json"`
            # had `upgrade` rewrite the ledger in a directory git cannot restore.
            #
            # The anchor is the project root the CLI resolved and `KEELLINE_DIRECTORY` above, a
            # constant in the installed package; the clone authors the value and nothing else.
            # No configured path belongs there: the preset puts none, and every file Keelline
            # keeps in it is found by a constant, never through `[paths]`.
            raise PathEscape(
                f"paths.{name} names Keelline's own directory {KEELLINE_DIRECTORY}, which holds "
                "its manifest and state git never sees and is not a place for a configured path"
            )
    return {
        name: contained(
            root,
            relative,
            allow_final_symlink=(name == "memory"),
            resolved_root=resolved_root,
        )
        for name, relative in config.paths.as_dict().items()
    }
