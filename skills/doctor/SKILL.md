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
3. A `skip` is not a fault, and it is not always harmless either. Three checks cannot be
   answered by this build at all — the release's recorded file hashes, whether a hook is
   trusted on Codex, and a `[ci]` reference nothing writes yet. Five more skip on a state of
   the machine: `wrapper` and `files` when no plugin root can be vouched for, `pre-commit` with
   no overlay root recorded, `bundles` and `store-debris` when the note store does not resolve,
   and `diagnostics` with no harness data root set. Each says which of the two it is in its own
   detail. Report the three as "nothing to answer here"; report the five as the state they name.
4. **`files` and `wrapper` skipping together is the report's loudest finding, and it is not
   red.** It means this process could not find the plugin — so no hook entry reaches Keelline
   on this machine, and nothing else in the report can say so. Lead with it, and relay the
   remedy both rows carry.
5. When `not-initialised` is red, every other row skips against it. Relay the red row and stop;
   the fourteen skips below it are not fourteen problems.
