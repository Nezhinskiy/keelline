"""Contract for the background-cleanup guard, driven through `judge`.

The command this guard exists to refuse was measured on 2026-09-02: a session backgrounded
fourteen busy-loop subshells with a bare ``&`` and expressed the cleanup as a LATER LINE of
the same command. The harness reaped the parent shell before that line ran, the subshells
re-parented to PID 1, and they burned 7.4 of 10 cores for 39 minutes with no writer left to
stop them. A trailing ``kill`` line is not cleanup; ``trap ... EXIT`` is.
"""

from __future__ import annotations

import re
import shlex

import pytest

from keelline.guards.bgcleanup import ALLOW, LEAK_REASON, RESTORE_HINT, SLEEP_REASON, judge

# The command from the incident, verbatim.
_INCIDENT = """for i in $(seq 1 14); do (while :; do :; done) & done
LOADPIDS=$(jobs -p)
sleep 2
PYTHONPATH=$PWD/src .venv/bin/python .../rate.py 15 2>&1 | grep -E '^idle|^under|failures'
kill $LOADPIDS 2>/dev/null"""


def denied(command: str, *, background: bool = True) -> bool:
    return judge(command, background=background).deny is not None


def hint(command: str) -> str | None:
    return judge(command, background=False).hint


def test_the_incident_command_is_denied() -> None:
    assert denied(_INCIDENT)


def test_the_incident_command_with_a_trap_is_allowed() -> None:
    """The same command, with the cleanup moved into a trap. This is the remedy the deny
    names, so it has to actually be accepted -- a guard whose stated fix is also refused
    teaches people to work around the guard rather than to fix the command."""
    remedied = _INCIDENT.replace(
        "LOADPIDS=$(jobs -p)",
        "LOADPIDS=$(jobs -p)\ntrap 'kill ${=LOADPIDS}' EXIT INT TERM",
    ).replace("\nkill $LOADPIDS 2>/dev/null", "")

    assert judge(remedied, background=True) == ALLOW


def test_the_incident_command_in_the_foreground_is_allowed() -> None:
    """The rule is keyed on `run_in_background`, and that is what holds false positives near
    zero. A foreground command's trailing `kill` line is reached because the tool is waiting
    on the very shell that runs it."""
    assert judge(_INCIDENT, background=False) == ALLOW


def test_a_command_with_no_ampersand_at_all_is_allowed() -> None:
    assert judge("PYTHONPATH=src .venv/bin/python -m pytest -n 8", background=True) == ALLOW


def test_a_chain_is_not_read_as_backgrounding() -> None:
    """`&&` is one compound token, not two `&`. A regex over raw text gets this wrong, which
    is why the check reads tokens."""
    assert judge("make && make test", background=True) == ALLOW


def test_a_redirect_is_not_read_as_backgrounding() -> None:
    """`2>&1` tokenizes to `['cmd', '2', '>&', '1']` -- the `>&` is its own compound token and
    no bare `&` is produced."""
    assert judge("pytest -q 2>&1 | tail -5", background=True) == ALLOW


def test_a_redirect_and_a_real_background_together_are_told_apart() -> None:
    """The discriminating case for the three shapes at once: this command contains `>`, `2>&1`
    AND a genuine backgrounding `&`. With a trap it is allowed; the test below removes only
    the trap and the same command denies, so the deny is attributable to the missing cleanup
    and not to any of the redirects."""
    with_trap = "trap 'kill ${=PID}' EXIT INT TERM; server >file 2>&1 & PID=$!; sleep 1"

    assert judge(with_trap, background=True) == ALLOW


def test_the_same_redirecting_command_without_its_trap_is_denied() -> None:
    without_trap = "server >file 2>&1 & PID=$!; sleep 1; kill $PID"

    assert denied(without_trap)


def test_a_lone_backgrounded_server_is_denied_too() -> None:
    """The deliberate no-exemption decision, pinned so it is not silently rediscovered.

    A bare `&` on a command that is the only thing being run -- a server meant to outlive the
    shell -- is still refused, because `run_in_background: true` already backgrounds the whole
    command. The inner `&` therefore only adds a child the harness cannot track and the reap
    cannot collect."""
    assert denied("python -m http.server 8000 &")


def test_a_quoted_mention_of_a_trap_does_not_excuse_the_leak() -> None:
    """`echo 'trap ... EXIT'` tokenizes to `['echo', 'trap ... EXIT']` -- the quoted string is
    ONE token, so exact-token matching sees no trap. A substring test on raw command text
    would see one and allow a real leak."""
    assert denied("echo 'trap it on EXIT'; sleep 300 & wait")


def test_a_trap_past_a_bare_double_dash_does_not_count() -> None:
    """`--` ends option parsing, so those words are operands to `printf`, not a trap."""
    assert denied("sleep 300 & printf '%s\\n' -- trap EXIT")


def test_a_trap_naming_only_int_and_term_does_not_count() -> None:
    """`INT`/`TERM` are accepted ALONGSIDE `EXIT`, never instead of it: a reap is neither
    signal, so a trap that does not name `EXIT` would not have run in the incident either."""
    assert denied("trap 'kill ${=P}' INT TERM; sleep 300 & P=$!; wait")


def test_a_trap_inside_a_compound_statement_counts() -> None:
    """`for ...; do trap ...; done` gives a segment whose first token is the keyword `do`, so
    an argv0-keyed test would miss the trap and wrongly deny a command that cleans up."""
    command = "for i in 1 2; do trap 'kill ${=P}' EXIT; sleep 9 & P=$!; done; wait"

    assert judge(command, background=True) == ALLOW


def test_a_background_hidden_in_a_shell_c_string_is_denied() -> None:
    """A `-c` string is ONE token however long the command inside it is, so without recursion
    this command's tokens say nothing but `bash`."""
    assert denied("bash -c 'sleep 300 & wait'")


def test_a_background_hidden_in_a_shell_fed_heredoc_is_denied() -> None:
    """A heredoc body with a QUOTED delimiter is removed from the scanned text entirely, so
    this too presents nothing but the word `bash` unless the body is read as the program it
    is."""
    command = "bash <<'EOF'\nsleep 300 &\nwait\nEOF"

    assert denied(command)


def test_a_heredoc_written_to_a_file_is_data_not_a_program() -> None:
    """`cat > file <<'EOF'` writes its body; it does not run it. Reading it as a program would
    make this plugin's own fixture authoring -- including this test file -- undeniable."""
    command = "cat > /tmp/x.sh <<'EOF'\nsleep 300 &\nEOF"

    assert judge(command, background=True) == ALLOW


def test_a_malformed_command_is_allowed_rather_than_refused() -> None:
    """An unbalanced quote is a command no shell would run. The judge allows it: the token
    it needs is `&`, the one thing a raw-text scan provably gets wrong, so there is no
    fail-closed fallback that would not refuse ordinary quoted text."""
    assert judge("sleep 300 & echo 'unbalanced", background=True) == ALLOW


def test_an_ampersand_inside_a_quoted_argument_is_not_backgrounding() -> None:
    """The likeliest accidental false positive, and the one a raw-text scan would hit hardest:
    a URL's query separators. `curl 'https://h/p?a=1&b=2'` contains two `&` characters and
    backgrounds nothing -- the tokenizer keeps the quoted argument as ONE token, so no bare
    `&` is produced."""
    assert judge('curl -s "https://h/p?a=1&b=2&c=3" | jq .', background=True) == ALLOW


def test_a_background_welded_to_a_closing_paren_is_denied() -> None:
    """`(sleep 300 &)` is THE deliberate-detach idiom, and it is exactly the leak this guard
    exists to refuse. `shlex`'s `punctuation_chars` mode fuses adjacent punctuation into one
    token, so the `&` arrives welded as `&)` and a membership test on the raw token list never
    sees it. `bashscan` already paid for this lesson once -- its header records
    "A SEPARATOR WELDED TO ITS NEIGHBOUR IS STILL A SEPARATOR".

    What this no longer measures, said here so the docstring is not read as a promise it does
    not keep: the ported `_begins_with_sleep` skips the leading `(`, so this command meets the
    `sleep` rule before the `&` scan and would be refused even with the weld unread.
    `test_a_non_sleep_background_welded_to_a_closing_paren_is_denied` below is the test that
    still proves the weld is seen, and it is the one the mutation entry names."""
    assert denied("(sleep 300 &)")


def test_a_non_sleep_background_welded_to_a_closing_paren_is_denied() -> None:
    """The same weld with a program the `sleep` rule does not already refuse.

    Not in the source, and needed only because of what changed in the port: the ported
    `_begins_with_sleep` skips a leading `(`, so `(sleep 300 &)` now meets the `sleep` rule
    first and is denied whether or not the weld is read at all. It can no longer prove the
    weld is seen; this can, because `LEAK_REASON` is reachable for this command only through
    the decomposition of `&)` into two pieces."""
    assert judge("(python -m http.server 8000 &)", background=True).deny == LEAK_REASON


def test_the_incident_command_denies_without_the_space_before_the_ampersand() -> None:
    """The module docstring's own incident command with ONE space deleted. A guard that
    catches the incident only when its author happened to type a space is not catching the
    incident."""
    welded = _INCIDENT.replace("done) & done", "done)& done")
    assert welded != _INCIDENT, "the fixture no longer contains the shape under test"

    assert denied(welded)


def test_a_subshell_background_inside_another_subshell_is_denied() -> None:
    """`((cmd) & wait)` opens with the token `((` -- the same token arithmetic opens with.
    Pinned because the tempting fix for the arithmetic false positive (suppress `&` inside a
    `((` run) would silence this, which is a real leak and closer to the incident than
    arithmetic ever is."""
    assert denied("((sleep 300; sleep 1) & wait)")


def test_the_pipe_both_operator_is_not_backgrounding() -> None:
    """The negative control for the welded-separator fix. `|&` is bash's "pipe stdout and
    stderr"; `bashscan` deliberately leaves it out of its compound-operator table, so it
    decomposes to `['|', '&']` and a naive scan of the pieces would read it as backgrounding.
    Its `&` is part of a pipe operator, not the async operator."""
    assert judge("make 2>/dev/null |& grep -i warning", background=True) == ALLOW


def test_a_case_fallthrough_terminator_is_not_backgrounding() -> None:
    """The other piece-decomposition trap: `;&` and `;;&` end a `case` branch and fall
    through. They decompose to `[';', '&']` and `[';', ';', '&']`, and neither `&` is the
    async operator."""
    command = "case $x in a) echo a ;& b) echo b ;; esac"

    assert judge(command, background=True) == ALLOW


def test_a_plain_argument_after_a_shell_c_cluster_is_not_a_program() -> None:
    """A quoted argument must not lose its quoting by being re-tokenized as a program.

    For any `-c` cluster other than the exact `-c`, every remaining token used to be scanned
    as a command in its own right -- and `tokenize("https://h/p?a=1&b=2")` yields
    `['https://h/p?a=1', '&', 'b=2']`, a bare `&`. So a URL passed as an ordinary argument
    denied, contradicting `test_an_ampersand_inside_a_quoted_argument_is_not_backgrounding`
    which pins the identical shape at the top level."""
    command = "bash -lc 'echo hi' \"https://h/p?a=1&b=2\""

    assert judge(command, background=True) == ALLOW


def test_the_reasons_carry_the_neutral_remedy_and_no_repository_path() -> None:
    """Every reason is shown to whoever just had a command refused, in a repository this
    plugin has never seen. The positive half is what the neutralisation actually changed --
    the path regex alone is green against the unported source, whose residue was a sentence
    about two named test suites, not a path."""
    assert "parallelise the suite rather than wait on it" in LEAK_REASON
    for text in (LEAK_REASON, SLEEP_REASON, RESTORE_HINT):
        assert re.findall(r"(?:docs|scripts|src|tests)/[\w./-]+", text) == [], text
        assert "suite" not in text.replace("parallelise the suite", "")


def test_a_backgrounded_command_that_begins_with_sleep_is_refused() -> None:
    """`run_in_background: true` returns at once, whatever the command sleeps for. Measured: a
    session believed it had waited nine minutes across fifteen such calls while 39 s passed."""

    reason = judge("sleep 300; gh pr checks 1", background=True).deny
    assert reason is not None
    assert "returns immediately" in reason and "Monitor" in reason


@pytest.mark.parametrize(
    "command", ["/bin/sleep 30; gh pr checks 1", "FOO=1 sleep 30", "env sleep 30", "( sleep 30 )"]
)
def test_a_backgrounded_leading_sleep_is_refused_however_it_is_spelled(command: str) -> None:
    # None of these is adversarial; the source's exact `["sleep"]` comparison allowed all four.
    assert judge(command, background=True).deny == SLEEP_REASON


def test_a_sleep_inside_a_command_substitution_is_not_a_leading_sleep() -> None:
    """`X=$(sleep 5) pytest -q` does not begin with `sleep`; it begins with an assignment whose
    value a substitution computes. It segments to
    `['X=$', '(', 'sleep', '5', ')', 'pytest', '-q']`, so filtering EVERY `(` out of the first
    segment -- rather than dropping the leading run of them -- put `sleep` at the front and
    refused it. Measured on the shipped module before the fix: `SLEEP_REASON`. A false refusal
    of ordinary work is the failure this guard's whole degrade-toward-silence rule exists to
    avoid, and this is the one rule with no allow-side fallback behind it."""
    assert judge("X=$(sleep 5) pytest -q", background=True) == ALLOW


def test_a_foreground_sleep_is_not_this_guard_s_business() -> None:
    assert judge("sleep 5; ls", background=False) == ALLOW


def test_a_backgrounded_command_that_only_mentions_sleep_later_is_allowed() -> None:
    """Keyed on the FIRST simple command: `pytest … ; sleep 1` is not the misunderstanding."""

    assert judge(".venv/bin/python -m pytest tests/x.py; sleep 1", background=True) == ALLOW


def test_a_command_past_the_size_cap_is_allowed_unread() -> None:
    # D7's named bound. Tokenizing is quadratic in token length and every Bash call pays it;
    # a harness timeout on the one CLOSED handler would refuse a legitimate command.
    # The fixture leads with `echo`, not `sleep`: the `sleep` rule is judged before the `&`
    # scan, so a leading `sleep` would pin SLEEP_REASON and say nothing about the `&` rule.
    from keelline.guards.bgcleanup import MAX_COMMAND_CHARS

    at_the_cap = "echo " + "x" * (MAX_COMMAND_CHARS - len("echo  &")) + " &"
    assert len(at_the_cap) == MAX_COMMAND_CHARS
    assert judge(at_the_cap + "x", background=True) == ALLOW
    assert judge(at_the_cap, background=True).deny == LEAK_REASON


def test_a_trailing_restore_without_a_trap_is_warned_about() -> None:
    """Measured 2026-09-05: a foreground mutate-test-restore command outlived the 120 s
    timeout, was backgrounded by the harness and reaped before its restore line."""

    command = (
        "cp ci.yml ci.yml.bak; sed -i '' 's/a/b/' ci.yml; "
        ".venv/bin/python -m pytest tests/x.py; cp ci.yml.bak ci.yml"
    )
    context = hint(command)
    assert context is not None
    assert "trap" in context and "EXIT" in context and "cp ci.yml.bak ci.yml" in context


def test_a_restore_after_a_subshell_is_still_seen() -> None:
    """`(pytest); cp a.bak a` tokenizes with `);` fused; a split on bare separators misses the
    boundary and reads the restore as part of the subshell's command."""

    context = hint("cp a a.bak; (pytest); cp a.bak a")
    assert context is not None and "cp a.bak a" in context


@pytest.mark.parametrize(
    "options",
    ["-a", "-p", "--", "--preserve=all"],
)
def test_a_restore_written_with_options_is_still_seen(options: str) -> None:
    """`cp -a` and `cp -p` are how the measured mutate-test-restore is ORDINARILY written, and
    both were silent while the bare two-operand spelling -- the only one anyone had tested --
    warned. Reading `command[-1]` as the destination and `command[1]` as the source is true of
    exactly that one spelling: an option, a `--`, or a `-t` breaks both positions.

    `--preserve=all` is here for the long-option half: it must be dropped as an option WITHOUT
    consuming the operand behind it, which is the failure mode of treating every `-` token as
    something that takes an argument."""

    command = (
        f"cp {options} ci.yml ci.yml.bak; sed -i '' 's/a/b/' ci.yml; "
        f"pytest tests/x.py; cp {options} ci.yml.bak ci.yml"
    )

    context = hint(command)
    assert context is not None
    assert "ci.yml.bak ci.yml" in context


@pytest.mark.parametrize(
    "command",
    [
        "cp src/a.py build/a.py; make; cp build/a.py dist/a.py",
        "mv report.json reports/run1.json; pytest; mv reports/run1.json reports/final.json",
    ],
)
def test_a_chained_copy_is_not_a_restore(command: str) -> None:
    """The cry-wolf case, and the reason the match is a ROUND TRIP rather than "the last
    command's source is something an earlier one wrote".

    Both of these end by moving a file the command produced earlier and neither puts anything
    back -- the restore's destination is a THIRD path, not the backup's original. Under the
    weaker rule every chained copy and every staged rename warned, on a guard that reads
    foreground calls too. A guard that fires on ordinary work is one people learn to ignore."""

    assert hint(command) is None


@pytest.mark.parametrize(
    "command",
    [
        "cp a.yml b.yml backup/; pytest; cp backup/ a.yml",
        "mv -t reports/ report.json; pytest; mv reports/ report.json",
    ],
)
def test_a_backup_copied_into_a_directory_is_not_a_round_trip(command: str) -> None:
    """A directory destination -- said by a third operand or by `-t` -- means the backup lives
    at `DIR/<name>`, a path this reader does not construct, so there is no round trip to see.

    The `-t` row is the one that read a SOURCE as the destination: `mv -t reports/ report.json`
    put `report.json` into the set of things that had been backed up, which is the opposite of
    what the command did with it."""

    assert hint(command) is None


def test_the_suggested_trap_body_is_the_restore_and_nothing_more() -> None:
    """The hint tells the reader to install its text as a trap body, and the text is rebuilt
    from tokens the tokenizer has already stripped of quoting. Joining them with spaces gives
    back a DIFFERENT command whenever any operand needed quoting: here a correctly quoted
    filename containing `;` reappears as a command separator, so the suggested trap body ends
    at the `;` and the rest becomes a second command in the trap line.

    Asserted by re-parsing rather than by string equality: the trap line must be four words,
    and its body must carry exactly the restore's argv."""

    command = 'cp "a; touch /tmp/PWNED" a.bak && pytest -q; cp a.bak "a; touch /tmp/PWNED"'

    context = hint(command)
    assert context is not None
    suggested = re.search(r"`(trap .+?)` as the FIRST line", context)
    assert suggested is not None, context
    argv = shlex.split(suggested.group(1))

    assert argv[0] == "trap" and argv[2:] == ["EXIT", "INT", "TERM"], argv
    assert shlex.split(argv[1]) == ["cp", "a.bak", "a; touch /tmp/PWNED"], argv[1]


@pytest.mark.parametrize(
    "command",
    [
        "trap 'cp b a' EXIT; cp a b; sed -i '' 's/x/y/' a; pytest; cp b a",
        "cp a b",
        "pytest tests/x.py; cp report.xml /tmp/out/",
    ],
)
def test_restores_with_a_trap_or_with_nothing_to_restore_stay_silent(command: str) -> None:
    """A trap makes the last line cleanup; a lone `cp`, or a `cp` that copies output away
    rather than restoring a backup, is not the shape."""

    assert hint(command) is None


def test_a_restore_command_with_no_operands_is_judged_rather_than_raised() -> None:
    """`cp --` names nothing to move. In the source this was a crash into a fail-open handler;
    here the handler is CLOSED, so an exception would refuse the call -- the opposite failure,
    and the reason `judge` must return rather than raise on any string."""
    assert judge("cp ci.yml ci.yml.bak; pytest; cp --", background=False) == ALLOW
