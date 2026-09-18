---
name: doctor
description: Diagnose a Keelline installation — hooks, memory store, budgets, overrides and trust. Use when a hook is silent, memory does not arrive, a gate fails unexpectedly, or the user asks whether Keelline is set up correctly.
---

# Diagnosing an installation

1. Run `keelline doctor --json` and read the report: fifteen checks, each with a status, a
   detail and a remedy. Between them they answer whether the repository is initialised, whether
   the hook wrapper can reach Keelline at all, whether this checkout is attached and what shape
   its memory path has, every hook entry with its provenance, each budget the preset clamps, a
   bundle that does not fit its slots, the last reasons a hook failed, and an environment
   variable that is set and ignored.
2. Relay each finding with the remedy the report names, verbatim. Do not change settings or
   hook entries on the user's behalf — name the command that would.
3. A `skip` is not a fault. Three checks cannot be answered by this build — the release's
   recorded file hashes, whether a hook is trusted on Codex, and a `[ci]` reference nothing
   writes yet — and each says so in its own detail. Say so rather than treating it as red.
