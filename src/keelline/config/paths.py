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
repository `init` would not touch again and `upgrade` does not yet ship for. The two spellings
agreed for four review rounds, which is what a duplicated rule does until it does not.
`checked_components` is the single spelling now; the import goes subpackage-to-leaf, so `fsops`
stays the leaf the hook path depends on it being.
"""

from __future__ import annotations

from pathlib import Path

from keelline.config.schema import PATH_VALUE, Config
from keelline.errors import Refusal
from keelline.fsops import UnsafePath, checked_components


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


def validate_paths(config: Config, root: Path) -> dict[str, Path]:
    resolved_root = root.resolve()
    for name, relative in config.paths.as_dict().items():
        if not PATH_VALUE.match(relative):
            # Named and never quoted: this is the value a report would otherwise print.
            raise PathEscape(
                f"paths.{name} is not a plain relative path matching {PATH_VALUE.pattern}"
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
