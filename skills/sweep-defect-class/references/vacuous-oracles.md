# Ten ways an assertion turns out vacuous

An assertion proves something only if it can fail, and only if what it measures is mostly
the behaviour under test. Each shape below was caught the hard way; each has a tell.

1. **The bound is trivially true.** `elapsed >= budget` under a clock the test controls.
   Suspect any bound under a faked clock, and `>=` generally.
2. **The replacement was argued, not run.** A cause chain "excluded" regressions it never
   caught. Run the regression; do not reason about it.
3. **The corpus, not the assertion.** Sound over two hand-picked inputs, wrong over two
   hundred. Sweep the producer's own value set.
4. **The window, not the query.** A search piped through `head` proves presence, never
   absence.
5. **The harness, not the assertion.** A guard measured under an interpreter that cannot
   import it fails closed, so every probe reads as a refusal. Prove the harness can emit
   both verdicts.
6. **The sentinel, not the state.** A default substituted for `null` fires on an empty
   string too. Key on the state's own field and print the rows that are not what you expect.
7. **The quantity is contaminated.** The assertion discriminates but is dominated by a term
   unrelated to the claim. Decompose the interval; measure the narrow one.
8. **The needle is already in the input.** The output "contains" a value the input carried
   all along. Pair the positive with an exclusion of the falsehood, and score both sides.
9. **The expectation is read from the subject.** `expected = table[key]; assert rendered ==
   expected` moves both sides together under any edit to the table. Pin a literal beside it.
10. **The collection the expectation derives from went empty.** `set(x) <= set(y)` is true
    for an empty `x`. Never derive the expectation from the thing whose emptying is the
    change.

The rule that follows: name the concrete regression, make it, watch the assertion fail,
**one change per mutation**, and check *which* tests reddened and *why*. Write "reddened
its target alone" or redesign.
