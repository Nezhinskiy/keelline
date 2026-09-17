"""Where the shipped overlay tree is, and what `plan()` is handed for it.

`template_root()` is a function rather than a constant because `templates/` is read at
*runtime* — `overlay create --local` renders it — so the answer depends on how this Keelline
was installed. It resolves the way `scaffold.shipped_profiles()` already resolves `profiles/`:
the installed package first, a checkout second, and never a bare `Path(__file__).parents[n]`,
which answers for a source tree an installed Keelline does not have. The checkout fallback is
taken only when the directory three levels up actually looks like one, so a package sitting
beside somebody else's `templates/` cannot pick it up.

The package probe finds nothing today: `templates/` lives at the repository root, `pyproject`'s
`source-include` puts it in the sdist, and the wheel carries `src/` alone. It is asked first
anyway, because it is the only answer that will hold the day the tree moves inside the package,
and because a probe added later is a probe nobody remembers to add.
"""

from __future__ import annotations

from functools import partial
from importlib import resources
from pathlib import Path

from keelline.errors import Failure
from keelline.overlay.layout import OVERLAY_FILES
from keelline.scaffold import Kind, Template

TEMPLATES = "templates"
OVERLAY = "overlay"
# `src/keelline/overlay/template.py` → three parents up is the repository root, when this file
# is in a checkout at all. The same arithmetic and the same markers `scaffold.engine` uses.
_REPOSITORY_ROOT = 3
_CHECKOUT_MARKERS = ("pyproject.toml", ".git")


def _in_a_checkout(root: Path) -> bool:
    return any((root / marker).exists() for marker in _CHECKOUT_MARKERS)


def template_root() -> Path:
    """The directory `templates/overlay/` resolves to for this installation.

    A path is always returned, existing or not, so a caller that cannot find the tree can name
    where it looked instead of handling a `None`. `templates()` is where that becomes a refusal
    a user can act on.
    """
    package = resources.files("keelline").joinpath(TEMPLATES, OVERLAY)
    if isinstance(package, Path) and package.is_dir():
        return package
    checkout = Path(__file__).resolve().parents[_REPOSITORY_ROOT]
    if _in_a_checkout(checkout):
        return checkout / TEMPLATES / OVERLAY
    # Neither answer exists. The package candidate is what an installed Keelline should have
    # carried, so that is the path the refusal names: a `templates/` three levels above an
    # installed package belongs to whoever put it there and must not be read as this one.
    return Path(str(package))


def _render(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def templates() -> list[Template]:
    """One whole-file `Template` per shipped file, rendered from the tree at apply time.

    Every artifact is `Kind.TEMPLATE`: the overlay is a repository Keelline creates outright,
    so there is no file of somebody else's to merge a region or a keyed entry into. That is
    what makes `overlay upgrade` the engine's hash-and-skip rule rather than a second copy of
    it — an untouched file is refreshed, an edited one is skipped and named.
    """
    root = template_root()
    if not root.is_dir():
        raise Failure(
            f"the overlay template tree is not readable at {root}; this Keelline was installed "
            "without it, so `--local` cannot render one"
        )
    return [
        Template(
            id=relative,
            kind=Kind.TEMPLATE,
            target=relative,
            source=f"{OVERLAY}/{relative}",
            render=partial(_render, root / relative),
        )
        for relative in OVERLAY_FILES
    ]
