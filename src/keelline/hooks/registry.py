"""Every `keelline.<area>.hooks.register()` result, in area-name order, with no shared list.

Nothing keys or de-duplicates handlers by their own name: two areas may register the same
handler name and both run. What discovery does enforce is the event vocabulary and the policy
vocabulary, so a mistyped `event` or `policy` fails loudly here instead of shipping a guard
that never fires — or one that fires and fails open because `dispatch` cannot read its policy.
"""

from __future__ import annotations

from keelline.areas import area_modules
from keelline.errors import Refusal
from keelline.hooks.api import EVENTS, Handler, Policy


class UnknownHookEvent(Refusal):
    """A handler registered for an event name `api.EVENTS` does not carry."""


class UnknownHookPolicy(Refusal):
    """A handler whose `policy` is not a `Policy`, which `dispatch` would read as OPEN."""


def _known_policy(policy: object) -> bool:
    """Exactly what `dispatch`'s `handler.policy == Policy.CLOSED` will accept.

    Comparison, not `isinstance`: `Policy` is a StrEnum and `dispatch` compares by value, so a
    lane that builds a Handler from a configuration string hands us `"closed"` and must be
    accepted. Nor is this a membership test — `"closed" in set(Policy)` happens to be True only
    because `str` precedes `Enum` in the MRO and keeps `str.__hash__`; dropping the `str` mixin
    would silently start refusing correct policies. Mirroring `==` cannot drift that way.
    """
    return any(policy == member for member in Policy)


def discover() -> list[Handler]:
    handlers: list[Handler] = []
    for module in area_modules("hooks"):
        for handler in module.register():
            if handler.event not in EVENTS:
                raise UnknownHookEvent(
                    f"{module.__name__} registered handler {handler.name!r} for event "
                    f"{handler.event!r}, which no harness emits; "
                    f"known events: {', '.join(EVENTS)}"
                )
            if not _known_policy(handler.policy):
                raise UnknownHookPolicy(
                    f"{module.__name__} registered handler {handler.name!r} with policy "
                    f"{handler.policy!r}, which is not a Policy; a handler whose policy "
                    f"dispatch cannot read fails open. Known policies: "
                    f"{', '.join(member.value for member in Policy)}"
                )
            handlers.append(handler)
    return handlers
