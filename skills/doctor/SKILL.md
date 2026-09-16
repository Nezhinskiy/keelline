---
name: doctor
description: Diagnose a Keelline installation — hooks, memory store, budgets, overrides and trust. Use when a hook is silent, memory does not arrive, a gate fails unexpectedly, or the user asks whether Keelline is set up correctly.
---

# Diagnosing an installation

Written against the CLI contract; the command ships with the `hooks-core` lane and is not
available yet. If an invocation below is rejected as an unknown command, say so and
stop — do not improvise a substitute.

1. Run `keelline doctor --json` and read the report: not initialised; store unresolved and
   why; a hook whose last run failed, with its reason; a bundle that does not fit its slots;
   each budget override; an ignored environment variable; every hook entry with its
   provenance.
2. Relay each finding with the remedy the report names, verbatim. Do not change settings or
   hook entries on the user's behalf — name the command that would.
