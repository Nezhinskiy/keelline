"""What a session hears about the overlay it is bound to — or not bound to (§6.3, §12; P1).

This area registers it because the question is this area's: `binding_for` says whether a
repository is bound, and `unlinked_groups` whether its notes ever moved. `memory/hooks.py`
keeps its single `SessionStart` handler and the test that pins it.

Every line is fixed text with at most a count interpolated; the overlay's declared floor is
the one owner-authored string that prints, normalised the way it was validated. A repository
chooses `project.name`, `memory.groups`, `paths.memory` and its remote, and none of the four
appears here (Global Constraints; P9 says why `refusal_reason` is not used). `MEMORY_PATH_REFUSED`
is this module's own line and not `binding.MEMORY_GROUP_ESCAPES` relayed: the refusal's text is
bounded too, but a line that reaches the model is written where it is read, and the two agree
because both are fixed.

**At most once per session (`once_key`), and what it actually costs.** The matcher fires on
`startup`, `resume`, `clear` and `compact`, and this handler runs ahead of `worktree-link` in
area-name order inside an entry whose `timeout` is ten seconds for both of them.

`hooks/dispatch.py` banks a `once_key` only `if handler.once_key is not None and delivered`, and
`delivered` is `bool(result.context) or result.decision == Decision.DENY`. So the marker is laid
down exactly when this handler had something to say. A session that hears a line hears it once;
a **healthy** repository -- bound, linked, pushed, satisfied -- returns an empty result, banks
nothing, and is asked again on every one of those four events.

And it is the healthy path that pays for the `git`, which is the opposite of what this docstring
said for three rounds. `binding_for` asks `origin_remote` on every run, at `gitenv`'s five-second
cap; `overlay_sync`'s `git status` and `git rev-list` are two seconds each and sit under `if not
lines:`, so they are reached exactly when nothing above them found anything wrong. Nine seconds
against the entry's ten, on the repository with nothing to report, re-asked on every resume. The
skip is real but it is the other way round: a repository with a finding pays five seconds and
not nine, because the finding short-circuits the sync.

Changing that is `dispatch.py`'s to change, not this module's -- `once_key`'s semantics are
shared by every area's handlers -- so the note is here and the behaviour is not touched.

Every import below the vocabulary is inside the handler body: `tests/test_areas.py` asserts
that discovery in a clean interpreter leaves `keelline.config`, `keelline.presets` and
`keelline.release` out of `sys.modules`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from keelline.hooks.api import Handler, HookEvent, HookResult, Policy

if TYPE_CHECKING:
    from keelline.config.schema import Config

OVERLAY_MODE = "overlay"
NO_OVERLAY = (
    "keelline: memory.mode is overlay and this machine records no overlay; "
    "run `keelline setup --preset recommended --overlay <path>`"
)
NOT_ASKABLE = "keelline: the overlay binding could not be checked on this machine"
NOT_ATTACHED = (
    "keelline: this repository is not attached to the overlay this machine records; "
    "run `keelline attach --store <overlay>/projects/<project>/memory --check`"
)
REMOTE_MISMATCH = (
    "keelline: the overlay records a different remote under this project's name; "
    "run `keelline attach --check` before trusting it"
)
MEMORY_PATH_REFUSED = (
    "keelline: a memory path was refused for this repository, so its notes were not checked; "
    "`keelline doctor` says which"
)
REAL_DIRECTORIES = (
    "keelline: {count} memory group(s) are real directories rather than links into the overlay, "
    "so this session reads the repository's own copy; move them into the overlay and run "
    "`keelline attach`"
)
REQUIRES_UNREADABLE = (
    "keelline: the overlay's keelline.requires is not a form this Keelline reads; "
    "`keelline doctor` says which"
)
REQUIRES = (
    "keelline: the overlay requires Keelline {spec} and {running} is running; "
    "install a Keelline that satisfies it"
)
NO_UPSTREAM = (
    "keelline: the overlay's branch has no upstream, so nothing backs it up and no commit on it "
    "is pushed; it has {dirty} uncommitted change(s). Push it with -u"
)
UNPUSHED = (
    "keelline: the overlay has {ahead} unpushed commit(s) and {dirty} uncommitted change(s); "
    "push it so the other machine sees them"
)
# The two lines above are mutually exclusive, and that is the fix rather than a tidying.
# `Sync.ahead` is `None` when `git rev-list @{upstream}..HEAD` could not be answered, which for a
# branch with no upstream means *every* commit on it is unpushed -- the count is unknown, not
# zero. The sink read `if sync.ahead is None` and then, on the next `if`, formatted
# `ahead=sync.ahead or 0`, so a session with no upstream and a dirty tree heard "nothing backs it
# up" and "0 unpushed commit(s)" in one breath: the second sentence says the opposite of the
# first and is the one carrying a number. `NO_UPSTREAM` carries the dirty count itself so the
# no-upstream case still reports the half that is knowable, and `UNPUSHED` is reached only with
# a real `ahead` to print.
#
# This condition was parked twice during development as "the plan specified it exactly". The plan
# is the authority on what to build; it is not the authority on whether a sentence is true.


def _overlay_status(event: HookEvent, config: Config | None) -> HookResult:
    if config is None or event.project_root is None or config.memory.mode != OVERLAY_MODE:
        return HookResult()
    try:
        import keelline
        from keelline.attach.binding import MISMATCH, UNBOUND, binding_for, unlinked_groups
        from keelline.config.paths import PathEscape
        from keelline.errors import Failure, Refusal
        from keelline.memory.api import overlay_root
        from keelline.overlay.api import overlay_sync, requires_of, satisfies

        root = event.project_root
        try:
            overlay = overlay_root(None)
        except Failure:
            return HookResult(context=NOT_ASKABLE)
        if overlay is None:
            return HookResult(context=NO_OVERLAY)
        lines: list[str] = []
        try:
            binding = binding_for(root, config, machine=None)
        except (Failure, Refusal):
            return HookResult(context=NOT_ASKABLE)
        if binding.state == UNBOUND:
            lines.append(NOT_ATTACHED)
        elif binding.state == MISMATCH:
            lines.append(REMOTE_MISMATCH)
        try:
            real = unlinked_groups(root, config)
        except PathEscape:
            real = ()
            lines.append(MEMORY_PATH_REFUSED)
        if real:
            lines.append(REAL_DIRECTORIES.format(count=len(real)))
        spec = requires_of(overlay)
        if spec is not None:
            verdict = satisfies(spec, keelline.__version__)
            if verdict is None:
                lines.append(REQUIRES_UNREADABLE)
            elif not verdict:
                lines.append(REQUIRES.format(spec=spec, running=keelline.__version__))
        if not lines:
            sync = overlay_sync(overlay)
            if sync.asked:
                if sync.ahead is None:
                    lines.append(NO_UPSTREAM.format(dirty=sync.dirty))
                elif sync.dirty > 0 or sync.ahead > 0:
                    lines.append(UNPUSHED.format(ahead=sync.ahead, dirty=sync.dirty))
        return HookResult(context="\n".join(lines)) if lines else HookResult()
    # An open handler never costs a session (§5.3); `memory/hooks.py` keeps the same backstop.
    except Exception:
        return HookResult()


def register() -> list[Handler]:
    return [
        Handler(
            name="overlay-status",
            event="SessionStart",
            policy=Policy.OPEN,
            run=_overlay_status,
            once_key="overlay-status",
        )
    ]
