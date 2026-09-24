"""Where Keelline's own files sit inside a project, derived once from `[paths]`.

`[paths] keelline` is the directory Keelline's own project files go under, so that `uninstall`
can account for them and a reader can find them. The project's documents stay at their own
`[paths]` keys. Every other module asks this one for a derived location rather than spelling it.

An adoption document is an ordinary plan: it sits directly in `[paths] plans`, where `plan
check` and the trail already look, and the word `keelline` in its file name is what marks it
(`<date>-keelline-adoption.md`, `<date>-keelline-adoption-<slug>.md`). Nothing records one, so
a project may carry any number of them. `is_adoption_plan` and `ADOPTION_WORD` have no caller in
this release: they are the one spelling of that rule, for `keelline adopt begin`, which ships
later and recognises the plan it is handed by it.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from keelline.config.schema import Config

ADOPTION_WORD = "keelline"


def rules_file(config: Config, profile: str) -> str:
    """The project-relative path of a profile's rules.

    Only a location: `scaffold.engine.validate_sources` holds `profile` to `PROJECT_NAME`, and
    `contained()` decides whether the result may be written, as it does for every target.
    """
    return f"{config.paths.keelline}/rules/{profile}.md"


def is_adoption_plan(config: Config, path: str) -> bool:
    """Whether `path`, relative to the project root, names an adoption plan.

    A markdown file directly in `[paths] plans` whose name has `keelline` as one of its
    hyphen-separated words. The answer is about the spelling alone: whether the file exists,
    and whether the path stays inside the root, are the caller's to ask of `contained()`.
    """
    candidate = PurePosixPath(path)
    return (
        candidate.parent == PurePosixPath(config.paths.plans)
        and candidate.suffix == ".md"
        and ADOPTION_WORD in candidate.stem.split("-")
    )
