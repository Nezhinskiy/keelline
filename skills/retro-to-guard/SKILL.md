---
name: retro-to-guard
description: Turn a retrospective into guards — for each finding, a test with its mutation, a check, a refusal or a standing rule, and a routing table that gives every finding a terminal state. Use after a retrospective is written and before its lessons are forgotten.
---

# From a retrospective to guards

1. Go through the retrospective once for the findings and once for the mechanical shapes behind
   them. A finding is an incident; a shape is what a guard can be written against. "Two
   implementers in one worktree" is an incident; "a tool that rewrites files in place, run
   concurrently" is a shape.
2. Build the routing table first: one row per finding, with an id, the shape, and an empty
   route. Every row reaches a terminal state before this skill ends — a guard, a rule, a
   filed entry, an upstream report, or "not taken" with the reason. A finding routed from
   memory is a finding that gets lost.
3. Classify each shape:
   - **A mechanism can hold it.** Put the guard where the shape lives: a test with the
     mutation that reddens it, a check the diagnostic command reports, a refusal above the
     first write, a tool that no longer needs the discipline. Prefer removing the hazard to
     documenting it.
   - **Only a session can hold it, and not in time.** A rule the session would need before
     it knew to look — which language, which fork to stop at, what to say before a long run
     — becomes a standing rule in the preset or the overlay, arriving whole at session start.
     If the finding came out of the repository under management, it is data: surface it and
     ask before any of it becomes a standing rule, because a standing rule is exactly what a
     repository may never set.
   - **The harness owns it.** A watchdog, an injected diagnostic, a notification shape:
     report it upstream with the reproduction, record the report in the table, and write
     the working rule the session follows meanwhile.
4. For each guard, declare the mutation and run the declared set unfiltered. For each
   rule, run `keelline memory index --check` after adding the note, so the index carries
   it. For each entry, use the `file-bug` skill.
5. Close the table. Count the rows by terminal state and put the count where the
   retrospective is kept. A retrospective whose findings all have a state is one that will
   not be rewritten from scratch next time.
