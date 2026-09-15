#!/usr/bin/env python3
"""Apply each mutation `mutations.toml` declares and check that the named tests go red.

The plans ask that "every new assertion ships with the mutation that reddens it, or a sentence
saying why none exists", and until now those mutations existed only as English sentences inside
multi-thousand-line plan documents. A contributor could satisfy the rule only by hand-editing
source and reverting, and a reviewer had no way to check they had.

This is not a general mutation tester — `mutmut` is, and is far too slow to gate a pull request
on. It is the curated set: the guards whose *load-bearingness* has to be proven rather than
merely covered, which is exactly the distinction that let `fsops.open_within` be fully covered
by twelve tests and still contain nothing.

Each entry names one file, one exact substring to replace, and the tests that must fail when it
is. A mutation that survives — the tests still pass with the guard broken — is a finding, and so
is one whose `before` no longer appears in the file, because that means the assertion and the
line it is about have drifted apart.

Usage:

    uv run python scripts/mutation_oracle.py            # every declared mutation
    uv run python scripts/mutation_oracle.py fsops      # only those whose name or file matches

Exit codes match the rest of the project: 0 all held, 1 findings.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECLARATION = ROOT / "mutations.toml"


@dataclass(frozen=True)
class Mutation:
    name: str
    file: Path
    before: str
    after: str
    reddens: tuple[str, ...]


def declared() -> list[Mutation]:
    raw = tomllib.loads(DECLARATION.read_text(encoding="utf-8"))
    return [
        Mutation(
            name=str(entry["name"]),
            file=ROOT / str(entry["file"]),
            before=str(entry["before"]),
            after=str(entry["after"]),
            reddens=tuple(str(t) for t in entry["reddens"]),
        )
        for entry in raw.get("mutation", [])
    ]


def _tests_pass(targets: tuple[str, ...]) -> bool:
    """Run only the named tests, against a bytecode cache that cannot be stale.

    `PYTHONPYCACHEPREFIX` at a fresh empty directory, and this is not belt-and-braces — it is
    load-bearing, and CI found that out. A `.pyc` header records the source's mtime **truncated
    to whole seconds**, so two writes to one file inside the same second that leave it the same
    size are indistinguishable to the import system. Two of the mutations below happen to change
    `memory/notes.py` by exactly the same 20 bytes each; on a fast runner the second one was written
    within a second of the first one's restore, Python reused the bytecode compiled under the
    *first* mutation, and the second was reported as surviving when it does not.

    An oracle whose own failures look exactly like findings is worse than no oracle, so the
    cache is made unusable rather than merely discouraged: `PYTHONDONTWRITEBYTECODE` keeps the
    fresh directory empty, and an empty cache directory means every module is compiled from the
    source actually on disk.
    """
    with tempfile.TemporaryDirectory(prefix="keelline-oracle-") as cache:
        done = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "--no-header",
                *targets,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPYCACHEPREFIX": cache, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    return done.returncode == 0


def _check(mutation: Mutation) -> str | None:
    """`None` when the mutation was caught; the finding otherwise."""
    if not mutation.file.is_file():
        return f"{mutation.file.relative_to(ROOT)} does not exist"
    original = mutation.file.read_text(encoding="utf-8")
    occurrences = original.count(mutation.before)
    if occurrences == 0:
        return (
            "its `before` line is not in the file any more — the assertion and the line it is "
            "about have drifted apart, so update the entry or delete it"
        )
    if occurrences > 1:
        return f"its `before` line appears {occurrences} times; make it unique"
    mutation.file.write_text(original.replace(mutation.before, mutation.after), encoding="utf-8")
    try:
        survived = _tests_pass(mutation.reddens)
    finally:
        mutation.file.write_text(original, encoding="utf-8")
    if survived:
        return f"survived — {', '.join(mutation.reddens)} still passed with the guard broken"
    return None


def main(argv: list[str]) -> int:
    pattern = argv[0] if argv else ""
    mutations = [
        m for m in declared() if not pattern or pattern in m.name or pattern in str(m.file)
    ]
    if not mutations:
        print(f"no mutation matches {pattern!r}", file=sys.stderr)
        return 1
    # A dirty tree would be restored to the wrong bytes if this is interrupted between the write
    # and the `finally`, and the restore writes the file it read — so refuse rather than risk it.
    status = subprocess.run(  # noqa: S603
        ["git", "status", "--porcelain", "--", *{str(m.file) for m in mutations}],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if status.returncode == 0 and status.stdout.strip():
        print(
            "refusing to mutate files with uncommitted changes:\n" + status.stdout,
            file=sys.stderr,
        )
        return 1

    findings: list[str] = []
    for mutation in mutations:
        finding = _check(mutation)
        mark = "caught " if finding is None else "FINDING"
        print(f"{mark}  {mutation.name}")
        if finding is not None:
            findings.append(f"{mutation.name}: {finding}")
    print()
    if findings:
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(f"\n{len(findings)} of {len(mutations)} mutations were not caught", file=sys.stderr)
        return 1
    print(f"all {len(mutations)} mutations were caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
