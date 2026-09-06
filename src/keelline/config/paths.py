"""Root containment for every path a repository-controlled file can name (§7.4)."""

from __future__ import annotations

from pathlib import Path

from keelline.config.schema import Config
from keelline.errors import Refusal


class PathEscape(Refusal):
    """A configured path that leaves the project root or passes through a symlink."""


def contained(
    root: Path,
    relative: str,
    *,
    allow_final_symlink: bool = False,
    resolved_root: Path | None = None,
) -> Path:
    candidate = Path(relative)
    if not candidate.parts:
        raise PathEscape("a path must name something inside the project root, not the root")
    if candidate.is_absolute():
        raise PathEscape(f"{relative!r} is absolute; paths must stay inside the project root")
    if any(part == ".." for part in candidate.parts):
        raise PathEscape(f"{relative!r} contains '..'; paths must stay inside the project root")
    target = root / candidate
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
    return {
        name: contained(
            root,
            relative,
            allow_final_symlink=(name == "memory"),
            resolved_root=resolved_root,
        )
        for name, relative in config.paths.as_dict().items()
    }
