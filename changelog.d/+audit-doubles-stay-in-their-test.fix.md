`keelline test audit-entrypoints` no longer reports a test as asserting on a double when the
value it checks comes from its real subject under a name that was a double somewhere else. Two
cases were reported:

- a different test in the same file bound the same name to a double. A double bound inside a
  test was treated as a module-level double, so in a file where one test wrote
  `sender = RecordingSender()` and another built its real subject under the same name, the
  second test's assertions on that subject were listed as `assert-on-double` candidates;
- the test itself bound the name to its real subject after it had been a double, either by
  shadowing a module-level double or by rebinding one of its own.

A double is now module-level only when it is bound at module scope, which still includes a
binding under a top-level `if`, `try` or `with`, and a binding in a test replaces whatever the
name held before it. `docs/cli.md` now defines what the command counts as a double.

The command's self-test now checks each of its known-bad samples for the shape that sample must
produce, rather than only checking that every shape appears somewhere, so losing one way to
detect a shape can no longer hide behind another sample that still produces it.
