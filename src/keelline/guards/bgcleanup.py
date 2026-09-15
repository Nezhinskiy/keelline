"""The background-cleanup judge: two refusals and one hint about a cleanup a reap can skip.

MEASURED 2026-09-02. A session reproducing a timing flake under CPU contention ran this as
ONE backgrounded command::

    for i in $(seq 1 14); do (while :; do :; done) & done
    LOADPIDS=$(jobs -p)
    sleep 2
    PYTHONPATH=$PWD/src .venv/bin/python .../rate.py 15 2>&1 | grep -E '^idle|^under|failures'
    kill $LOADPIDS 2>/dev/null

The harness reaped the parent shell before the `kill` line. The fourteen subshells were
`&`-backgrounded, so they survived, re-parented to PID 1, and busy-looped for 39 minutes at
~56% CPU each -- 7.4 of 10 cores -- until a later session found them. Their owning session had
ended and its PR had merged, so nothing was left that could ever have stopped them, and a
sibling session read the load as ambient contention and held a paid eval run waiting for it
to clear.

WHAT THIS FILE CANNOT FIX, stated so the boundary stays clear: the harness reaps the parent
shell without killing its process group. That is agent-harness behaviour, not repository
behaviour, and nothing here works around it.

WHAT IT CAN FIX is the command SHAPE, which is where the leak is actually authored. Cleanup
expressed as a trailing line of the same command is not cleanup -- it runs only if the shell
survives to reach it, which is exactly the assumption a reap breaks. `trap 'kill ...' EXIT INT
TERM` runs where a trailing line does not, because the shell fires it on the way out however it
leaves. So the rules below refuse that shape before it starts where refusing is right and
advise where it is not, each naming the remedy rather than the rule alone.

WHAT THIS MODULE DOES, three readings of that one shape:

1. It REFUSES a backgrounded command that leaks an `&` job with no trap (`LEAK_REASON`).
2. It REFUSES a backgrounded command whose FIRST simple command is `sleep` (`SLEEP_REASON`).
3. It ADVISES -- never refuses -- when a command's last line restores a backup outside a trap
   (`RESTORE_HINT`).

THE `&` RULE, all three conditions required:

1. The call carries `run_in_background: true`. Keying on the flag is what keeps false
   positives near zero: a foreground command that leaks is a much rarer accident, because the
   shell that would run the trailing line is the one the tool is waiting on.
2. The command backgrounds a job with a bare `&`. Read as a TOKEN from `bashscan.tokenize`,
   never as a regex over raw text -- `&&` and `2>&1` are precisely what a text scan gets
   wrong, and the tokenizer already resolves both (`a && b` -> `['a', '&&', 'b']`,
   `cmd 2>&1` -> `['cmd', '2', '>&', '1']`, neither yielding a bare `&`).
3. No `trap` naming `EXIT` anywhere in the command.

THE `sleep` RULE is one condition on top of the flag: the first simple command is `sleep`.
A backgrounded call returns at once -- the harness does not wait for it -- so the sleep buys
nothing and the check after it runs immediately, in the background, unread. Measured
2026-09-05: fifteen such calls, nine 'minutes' of sleeping, 39 seconds of wall clock. It
refuses rather than advises because there is no shape where a backgrounded leading `sleep`
does what its author meant. Only the FIRST command counts: `pytest ...; sleep 1` is not the
misunderstanding.

THE RESTORE HINT is the one behaviour NOT keyed on `run_in_background`, deliberately: the
shape it names was measured 2026-09-05 on a FOREGROUND call, which outlived the 120 s timeout,
was backgrounded by the harness and reaped before its restore line, leaving a workflow file
mutated. The flag cannot key it because at PreToolUse time the timeout has not happened. That
is also why its matching is the narrowest thing in this file: it reads every Bash call, so it
fires only on the ROUND TRIP -- an earlier `cp`/`mv` whose source and destination the last
command swaps back -- and stays silent on an ordinary chained copy (`cp src/a build/a; make;
cp build/a dist/a`), which shares the last command's shape and restores nothing. It is advice
and never a refusal, so a miss costs nothing and a false fire is noise on every `cp` anyone
writes.

NO EXEMPTION FOR A LONE `cmd &`, and this was the one judgement call the rule left open: should
a bare `&` on a command that is itself the only thing being run -- a server the caller means to
outlive the shell -- be allowed? It is not, because under `run_in_background: true` the harness
ALREADY backgrounds the whole command. An inner `&` therefore adds nothing but a child the
harness cannot track and the reap cannot collect: either it is redundant (drop it, and the tool
still backgrounds the command) or it is the leak (a server nothing will reap is the same defect
as fourteen busy-loops nothing will reap, differing only in how much CPU it burns). There is no
shape where the inner `&` is both necessary and safe, so there is nothing to exempt.
`test_a_lone_backgrounded_server_is_denied_too` pins the decision rather than leaving it to be
rediscovered.

DEGRADES TOWARD SILENCE at every seam where it can degrade at all, with ONE measured
exception named below: an unparseable command is allowed, a trap this reads too generously is
allowed, and a `&` nested past the recursion bound is allowed. That direction is deliberate.
This guard exists to stop a shape people write BY ACCIDENT, not to hold a line against someone
spelling around it -- and a guard that fires on ordinary work is one people learn to route
around rather than obey.

THE EXCEPTION, stated rather than left for someone to trip over: a BITWISE `&` inside an
arithmetic expansion is refused. `echo $((3 & 1))` tokenizes to
`['echo', '$', '((', '3', '&', '1', '))']`, and that `&` is bare. The obvious fix -- suppress
`&` inside a run opened by `((` -- was measured and rejected, because `((` is not unambiguous:
`((sleep 1; sleep 2) & wait)` opens with the same token, and suppressing there would silence a
REAL leak that is far closer to the incident than any arithmetic is
(`test_a_subshell_background_inside_another_subshell_is_denied` pins that shape). Refusing a
rare bitwise expression is the cheaper error of the two, and backgrounding one is not a thing
anyone does on purpose.

WHAT IS NOT COVERED, recorded rather than implied:

- BY EITHER REFUSAL, a command the harness moves to the background ITSELF, after the
  foreground timeout, with no `run_in_background` in the payload. The flag is the only signal
  available at PreToolUse time; the timeout has not happened yet and nothing in the input
  predicts it. The restore hint is the one behaviour that does not need the flag, and it is
  unkeyed for exactly this reason.
- `trap - EXIT`, which REMOVES a trap rather than installing one, reads here as a trap and
  allows. Distinguishing it is one condition, and it is deliberately not written: it buys
  nothing against an accident, and every line spent narrowing the trap test is a line that can
  produce a false refusal on a real trap spelled unusually.
- A `&` inside a `$(...)` substitution, or in a body fed to a LANGUAGE interpreter rather than
  a shell (`python3 - <<'PY'`). The first is exotic -- a substitution's output is captured, so
  backgrounding inside one is not a shape that occurs by accident -- and the second is not
  shell grammar, so re-reading it as shell would be judging the wrong language.
- A shell `-c` command string that another option in the same cluster displaces, as in
  `bash -cO extglob '<command>'`. `_nested_programs` takes the token after the cluster and
  only that one; reading further was measured to REFUSE ordinary quoted arguments, which is
  the wrong direction to be wrong in.
- A backup copied INTO A DIRECTORY (`cp ci.yml bak/`, `cp -t bak ci.yml`, `cp a b bak`). The
  backup then lives at `bak/ci.yml`, a path this reader would have to construct rather than
  read, so no round trip can be recognised and the hint stays silent. Recorded rather than
  built: guessing the joined path is the kind of reach that turns a hint into noise.
- A restore line carrying a redirect (`cp a.bak a 2>/dev/null`), on either side of the round
  trip. `segments` keeps the redirect pieces in the segment and this reader counts them as
  operands, so the command looks multi-operand and comes back silent -- verified both ways
  rather than assumed.
- A command longer than `MAX_COMMAND_CHARS`, which is not read at all. See that constant.
"""

from __future__ import annotations

import re
import shlex
from itertools import dropwhile
from pathlib import Path
from typing import NamedTuple

from keelline.guards import bashscan


class Verdict(NamedTuple):
    """What the guard says about one Bash call: a refusal reason, an advisory, or neither."""

    deny: str | None
    hint: str | None


ALLOW = Verdict(None, None)

# D7: a cap, not a config key. Above it the guard does not read the command at all. 64 KiB is
# far past any command a person or a model types and far below where tokenizing costs seconds.
MAX_COMMAND_CHARS = 65_536

# The backgrounding operator, as an operator PIECE. `bashscan.tokenize` emits `&&`, `>&`,
# `&>` and `&>>` as their own compound tokens, so none of them can be mistaken for this --
# which is the whole reason this check reads tokens instead of text.
_BACKGROUND_OPERATOR = "&"

# Pieces that, standing immediately before an `&`, mean that `&` is part of a LONGER operator
# rather than the async one. `|&` (pipe stdout and stderr), `;&` and `;;&` (case fall-through)
# are deliberately absent from `bashscan._COMPOUND_OPERATORS`: for SEGMENTATION every
# piece of them ends a command, so letting them fall through to single characters yields the
# right number of breaks with no extra table. That is correct there and wrong here, so this
# file reads the pieces and then interprets them -- a naive scan for a `&` piece would refuse
# `cmd |& grep x`, which backgrounds nothing.
_COMMAND_ENDING_PIECES = frozenset({"|", ";"})

# `trap ACTION SIGNAL...`. Both words are matched as EXACT TOKENS, which is what separates an
# installed trap from a mention of one: `echo 'trap ... EXIT'` tokenizes to
# `['echo', 'trap ... EXIT']` -- the quoted string is ONE token, matching neither -- while
# `trap 'kill ${=PIDS}' EXIT INT TERM` tokenizes to
# `['trap', 'kill ${=PIDS}', 'EXIT', 'INT', 'TERM']`. `INT`/`TERM` are accepted alongside by
# saying nothing about them: only `EXIT` is required, and extra signals are extra tokens.
_TRAP = "trap"
_EXIT_SIGNAL = "EXIT"

# `--` ends option parsing by the same getopt convention every tool here follows, so tokens
# after it are operands rather than words the shell or a command interprets. Without the
# cutoff, `printf '%s\n' -- trap EXIT` would read as a trap and excuse a real leak.
_OPTION_TERMINATOR = "--"

# Shells whose `-c <string>` argument is itself a shell command line, and whose heredoc body
# is a program rather than data. Membership rule: does this binary accept `-c <string>` and
# execute the string as a command line?
_SHELL_INTERPRETERS = frozenset(
    {"ash", "bash", "csh", "dash", "fish", "ksh", "mksh", "rbash", "sh", "tcsh", "zsh"}
)

# A single-dash short-option cluster containing `c`: `-c`, and equally `-lc`, `-ic`. Anchored
# at both ends so a long option (`--check`, `--color`) and an inline value (`-I{}`) never
# match.
_SHELL_C_FLAG = re.compile(r"\A-[A-Za-z]*c[A-Za-z]*\Z")

# D7: a cap on descent into a command hidden inside a string, not a config key. Real nesting
# rarely goes past one level. Exceeding it stops looking, which ALLOWS, and that direction is
# deliberate: it risks a leak in a shape -- a shell inside a shell inside a shell -- nobody
# reaches by accident, while denying on depth alone would refuse legitimate deep nesting that
# carries no `&` this reader can see.
_MAX_RECURSION_DEPTH = 3

LEAK_REASON = (
    "This command backgrounds a job with `&` and expresses its cleanup as a later line of "
    "the same command. That is not cleanup: the harness can reap the parent shell before the "
    "line is reached, and an `&`-backgrounded child survives the reap, re-parents to PID 1, "
    "and runs until something finds it. Measured 2026-09-02: fourteen busy-loop subshells "
    "leaked this way burned 7.4 of 10 cores for 39 minutes, and the session that started them "
    "had already ended.\n"
    "Do one of these instead:\n"
    "- Put the cleanup in a trap, which runs however the shell exits: "
    "`trap 'kill ${=PIDS}' EXIT INT TERM`. Note `${=PIDS}` and not `$PIDS` -- zsh does not "
    "word-split an unquoted parameter, so `kill $PIDS` passes the whole list as ONE argument "
    "and silently fails.\n"
    "- Or do not background the helper at all. This call already carries "
    "`run_in_background: true`, so the harness is backgrounding the whole command for you; an "
    "inner `&` only adds a child that nothing can reap.\n"
    "- Best of all, size the run to finish in the foreground: parallelise the suite "
    "rather than wait on it."
)

SLEEP_REASON = (
    "This command is backgrounded (`run_in_background: true`) and begins with `sleep`. A "
    "backgrounded call returns immediately -- the harness does not wait for it -- so the sleep "
    "buys nothing and the check after it runs at once, in the background, unread. Measured "
    "2026-09-05: fifteen such calls, nine 'minutes' of sleeping, 39 seconds of wall clock.\n"
    "To wait for a condition, use the Monitor tool with an until-loop, or run the check in the "
    "foreground without the sleep."
)

# `{trap}` carries its own quoting -- the template must NOT wrap it in literal quotes. The
# text is rebuilt from tokens that have already lost theirs, so `cp a.bak "a; touch x"` would
# otherwise be handed back as `trap 'cp a.bak a; touch x' EXIT`: a DIFFERENT command, and one
# whose trap body ends at the `;`. `shlex.quote` per token restores an argv-equivalent line,
# and quoting that line again makes it one word for `trap`. The cost, recorded because it is
# real: a restore that meant to expand something (`cp $BAK $ORIG`) comes back quoted and inert.
# The tokens carry no memory of their quoting, so one of the two readings had to lose, and an
# over-quoted suggestion is visibly wrong to whoever reads it while an under-quoted one runs.
RESTORE_HINT = (
    "This command restores a backup on its last line (`{restore}`). That line runs only if the "
    "shell survives to reach it: a foreground call that outlives the 120 s timeout is "
    "backgrounded by the harness and may be reaped before it, leaving the tree mutated -- "
    "measured 2026-09-05 on a workflow file. Put the restore in a trap, which runs however the "
    "shell exits: `trap {trap} EXIT INT TERM` as the FIRST line."
)

_RESTORE_COMMANDS = frozenset({"cp", "mv"})

# `cp`/`mv` options that name the destination instead of leaving it as the last operand.
# Without them `mv -t reports/ report.json` reads its SOURCE as the destination, which is the
# opposite of what it is.
_TARGET_DIRECTORY_OPTIONS = frozenset({"-t", "--target-directory"})


def judge(command: str, *, background: bool) -> Verdict:
    """The whole contract, as a pure function of the command text and the background flag.

    It never raises on a string input. The handler that calls it is `Policy.CLOSED`, so an
    exception here would refuse an ordinary call -- the opposite of the failure this guard
    exists to prevent, and the reason every seam below degrades toward silence instead.
    """
    if len(command) > MAX_COMMAND_CHARS:
        return ALLOW
    if background:
        tokens = bashscan.tokenize(command)
        if tokens is not None and _begins_with_sleep(tokens):
            return Verdict(SLEEP_REASON, None)
        backgrounds, traps = _scan(command, depth=0)
        if backgrounds and not traps:
            return Verdict(LEAK_REASON, None)
    return Verdict(None, _restore_hint(command))


def _begins_with_sleep(tokens: list[str]) -> bool:
    """The first simple command's program is `sleep`, however it is spelled.

    An exact `commands[0][:1] == ["sleep"]` comparison is the bare spelling and no other, so
    `/bin/sleep 30`, `FOO=1 sleep 30`, `env sleep 30` and `( sleep 30 )` all passed it, and
    none of them is adversarial. `command_words` resolves the assignment and wrapper prefixes;
    `Path(...).name` resolves the absolute path.

    `dropwhile`, NOT a filter over the whole segment, and the difference is a measured false
    refusal rather than a nicety. A LEADING `(` is skipped because a subshell opens the same
    command, but `X=$(sleep 5) pytest -q` segments to
    `['X=$', '(', 'sleep', '5', ')', 'pytest', '-q']`, and dropping every `(` in it put
    `sleep` at the front of a command that does not begin with `sleep` at all -- a refusal on
    ordinary work, from a `Policy.CLOSED` handler, on the one rule that has no allow-side
    fallback. A `sleep` inside a substitution is not a leading `sleep`; after the leading run
    of `(` the first word decides, and here that word is the assignment's own token.

    STILL MISSED, recorded rather than implied: `time sleep 30`, and any other prefix command
    outside `command_words`' two tables.
    """
    commands = bashscan.segments(tokens)
    if not commands:
        return False
    words = bashscan.command_words(list(dropwhile(lambda t: t == "(", commands[0])))
    return bool(words) and Path(words[0]).name == "sleep"


def _restore_hint(command: str) -> str | None:
    """Advice, never a refusal: a trailing restore with no trap, foreground or not."""
    tokens = bashscan.tokenize(command)
    if tokens is None or _installs_an_exit_trap(tokens):
        return None
    restore = _restores_at_the_end(tokens)
    if not restore:
        return None
    return RESTORE_HINT.format(restore=restore, trap=shlex.quote(restore))


def _backgrounds_a_job(tokens: list[str]) -> bool:
    """Whether these tokens background a job with the async operator.

    The entire correctness of this check is that it is not a text search. `a && b`,
    `cmd 2>&1` and `cmd >file 2>&1 &` all contain the character `&`; only the last one
    backgrounds anything, and `bashscan.tokenize` is what tells them apart -- it emits
    `&&` and `>&` as single compound tokens, leaving a bare `&` to mean one thing.

    THE TOKEN LIST ALONE IS NOT ENOUGH, and testing `"&" in tokens` was a measured hole
    rather than a stylistic simplification. `shlex`'s `punctuation_chars` mode fuses a run
    of adjacent punctuation into ONE token, so `(sleep 300 &)` arrives as
    `['(', 'sleep', '300', '&)']` -- no bare `&` anywhere -- and the deliberate-detach idiom,
    the very thing this guard exists to refuse, was allowed. So was the module docstring's own
    incident command with a single space deleted (`done)& done`). `_installs_an_exit_trap`
    never had the problem because it goes through `bashscan.segments`, which decomposes such
    runs; this was the one place that skipped the decomposition. `bashscan`'s own header
    records the identical defect being fixed inside that module ("A SEPARATOR WELDED TO ITS
    NEIGHBOUR IS STILL A SEPARATOR"), so the lesson was available and simply not applied here.

    Interpreting the pieces, rather than just scanning them, is the other half. `|&`, `;&` and
    `;;&` decompose to single characters by design, and each of their `&`s belongs to a pipe
    or a case fall-through, never to an async operator -- so a `&` directly preceded by `|` or
    `;` is skipped. See `_COMMAND_ENDING_PIECES`.
    """
    for token in tokens:
        pieces = bashscan.operator_pieces(token)
        for index, piece in enumerate(pieces):
            if piece != _BACKGROUND_OPERATOR:
                continue
            if index and pieces[index - 1] in _COMMAND_ENDING_PIECES:
                continue
            return True
    return False


def _installs_an_exit_trap(tokens: list[str]) -> bool:
    """Whether these tokens install a `trap` naming `EXIT`.

    Scanned per SEGMENT so the two words have to belong to the same simple command:
    `echo trap && echo EXIT` is two commands and neither is a trap. Within a segment the
    scan is positional rather than argv0-keyed, because a trap is routinely written inside
    a compound statement -- `for i in 1 2; do trap 'x' EXIT; done` gives a segment whose
    first token is the keyword `do`, and an argv0 test would miss it and wrongly deny.

    Reading a trap too generously ALLOWS, which is the safe direction here and the reason
    the looser positional test is the right one: the cost of a false trap is a leak that
    was already going to happen, while the cost of a missed trap is refusing a command
    that did the correct thing.
    """
    for segment in bashscan.segments(tokens):
        seen_trap = False
        for token in segment:
            if token == _OPTION_TERMINATOR:
                break
            if token == _TRAP:
                seen_trap = True
            elif seen_trap and token == _EXIT_SIGNAL:
                return True
    return False


class _Copy(NamedTuple):
    """What a `cp`/`mv` simple command moves, once its options are out of the way."""

    sources: tuple[str, ...]
    destination: str
    into_directory: bool


def _copy_operands(command: list[str]) -> _Copy | None:
    """A `cp`/`mv` command's operands, or None when it has too few to move anything.

    OPTIONS FIRST, because position alone is not the answer and reading it as one was the
    defect this replaced: `command[-1]` is the destination only for the zero-option spelling.
    `cp -a X X.bak` and `cp -p X X.bak` are how the measured incident ("mutate, test,
    restore") is ordinarily written, and both were invisible; `mv -t DIR src` was worse than
    invisible, reading a SOURCE as the destination.

    The split is deliberately shallow, and each decision is a direction to be wrong in:

    - Any token starting with `-` is an option and is dropped, INCLUDING a long option with an
      inline value (`--preserve=all`) -- which is why nothing here consumes a following token
      except the two that genuinely take one. A bare `-` is stdin/stdout, so it is an operand.
    - `--` ends option parsing, by the same getopt convention `_OPTION_TERMINATOR` already
      serves in this file; every token after it is an operand however it is spelled.
    - `-t DIR` / `--target-directory[=]DIR` name the destination, and every operand is then a
      source. NOT the inline cluster spelling `-tDIR`, which is dropped whole -- option and
      value together -- leaving the remaining operands to be read positionally and the
      destination wrong (measured: `cp -tDIR a b` reports `b`). Unpacking short-option clusters
      is real work for a spelling nobody writes, `cp -t` being rare already, and what it leaves
      behind is one pair in the backups set that a round trip has to match exactly before
      anything is said. Recorded rather than fixed, in the direction this file records the
      rest of its misses.
    - FEWER THAN TWO OPERANDS and no `-t` (`cp --`, `cp --help`, `cp x`) is not a move at all:
      None, rather than an index error on a command that names no destination.

    `into_directory` records that the destination is a DIRECTORY rather than a file, which the
    command's own shape says two ways: `-t` always means one, and so does a third operand
    (`cp a b DIR` cannot mean anything else). The backup then lives at `DIR/<name>`, a path
    this reader does not construct -- see the module docstring's uncovered list.
    """
    operands: list[str] = []
    destination: str | None = None
    index = 1
    operands_only = False
    while index < len(command):
        token = command[index]
        index += 1
        # `noqa: S105` -- `token` here is a shell word off a command line, never a credential,
        # and `-` is the getopt spelling of stdin/stdout. The rule keys on the variable name.
        if operands_only or not token.startswith("-") or token == "-":  # noqa: S105
            operands.append(token)
        elif token == _OPTION_TERMINATOR:
            operands_only = True
        elif token in _TARGET_DIRECTORY_OPTIONS:
            destination = command[index] if index < len(command) else destination
            index += 1
        elif token.partition("=")[0] in _TARGET_DIRECTORY_OPTIONS and "=" in token:
            destination = token.partition("=")[2]
    if destination is not None:
        return _Copy(tuple(operands), destination, True) if operands else None
    if len(operands) < 2:
        return None
    return _Copy(tuple(operands[:-1]), operands[-1], len(operands) > 2)


def _restores_at_the_end(tokens: list[str]) -> str | None:
    """The trailing restore command as shell text, or None.

    A restore is a ROUND TRIP: `cp X X.bak` early and `cp X.bak X` last -- the same two paths,
    source and destination swapped back -- or a `git restore` / `git checkout --`. Matching the
    swap, rather than only the backup's destination reappearing as a source, is what separates
    a restore from an ordinary chained copy: `cp src/a build/a; make; cp build/a dist/a` and
    `mv r.json runs/1.json; pytest; mv runs/1.json runs/final.json` both end by moving a file
    the command wrote earlier, and neither puts anything back. Firing on those -- and on every
    `cp` that copies output away -- would be the cry-wolf guard people learn to route around.
    `segments`, not a split on bare separators: `(pytest); cp a.bak a` fuses `);` into one
    token, and only `segments` puts the restore in a command of its own.

    The returned text is rebuilt with `shlex.quote` per token, because the tokens reaching here
    have already lost their quoting and the hint invites the reader to run this text.
    """

    commands = bashscan.segments(tokens)
    if len(commands) < 2:
        return None
    last = commands[-1]
    if last[:2] == ["git", "restore"] or last[:3] == ["git", "checkout", "--"]:
        return _as_shell_text(last)
    if last[0] not in _RESTORE_COMMANDS:
        return None
    restore = _copy_operands(last)
    if restore is None or restore.into_directory:
        return None
    backups: set[tuple[str, str]] = set()
    for command in commands[:-1]:
        if command[0] not in _RESTORE_COMMANDS:
            continue
        backup = _copy_operands(command)
        if backup is None or backup.into_directory:
            continue
        backups.add((backup.sources[0], backup.destination))
    if (restore.destination, restore.sources[0]) in backups:
        return _as_shell_text(last)
    return None


def _as_shell_text(command: list[str]) -> str:
    """A tokenized command back as text a shell reads the same way this file read it."""
    return " ".join(shlex.quote(token) for token in command)


def _nested_programs(tokens: list[str], heredocs: list[bashscan.Heredoc]) -> list[str]:
    """Command text this command hands to a shell: `-c` strings and shell-fed heredoc bodies.

    Both are places a whole command line hides from the token stream. A `-c` string is ONE
    token however long the command inside it is, and a heredoc body with a QUOTED delimiter
    is removed from the text entirely by `bashscan.prepare` (which is what lets this
    project's own fixtures and tests be authored at all). So `bash -c 'sleep 9 & wait'` and
    `bash <<'EOF'` / `sleep 9 &` / `EOF` both present this guard with nothing but the word
    `bash` unless their contents are pulled back out and read as the programs they are.

    Only SHELL headers qualify for the heredoc half. A body fed to `cat`/`tee` is data being
    written to a file, and a body fed to `python3` is a different language -- reading either
    as a shell command line would be judging the wrong thing.
    """
    programs: list[str] = []
    for segment in bashscan.segments(tokens):
        shell: str | None = None
        for index, token in enumerate(segment):
            if Path(token).name in _SHELL_INTERPRETERS:
                shell = Path(token).name
            elif shell is not None and _SHELL_C_FLAG.match(token):
                # The NEXT token, for every cluster spelling. Taking "every remaining token"
                # for a non-exact cluster (`-lc`, `-ic`) was a measured WRONGFUL DENY, not the
                # inert over-reading its comment claimed: a candidate is re-tokenized without
                # its original quoting, and `tokenize("https://h/p?a=1&b=2")` yields a bare
                # `&`, so `bash -lc 'echo hi' "<that url>"` refused an ordinary argument --
                # contradicting the top-level shape pinned by
                # `test_an_ampersand_inside_a_quoted_argument_is_not_backgrounding`.
                # What this gives up is the shape where another option in the cluster consumes
                # the slot (`bash -cO extglob '<command>'`, where the command string is two
                # tokens away). That is a miss rather than a false refusal, which is the
                # direction this file degrades in everywhere else, and it is recorded in the
                # module docstring instead of being traded for a deny on ordinary work.
                programs.extend(segment[index + 1 : index + 2])
                shell = None
    for heredoc in heredocs:
        header = bashscan.tokenize(heredoc.header)
        if header is None:
            continue
        if any(
            Path(token).name in _SHELL_INTERPRETERS
            for segment in bashscan.segments(header)
            for token in segment
        ):
            programs.append(heredoc.body)
    return programs


def _scan(command: str, depth: int) -> tuple[bool, bool]:
    """`(backgrounds a job, installs an EXIT trap)` for `command` and everything nested in it.

    Both halves are collected over the WHOLE command tree rather than judged per simple
    command, because the question this guard asks is about the command as a whole: does it
    leave a process nothing will reap? A trap installed anywhere excuses a `&` written
    anywhere, which is both the shell's own reading -- an EXIT trap fires for the shell that
    installed it, whichever line backgrounded the job -- and the permissive direction.

    An unparseable command (unbalanced quotes) yields `(False, False)` and is therefore
    allowed. There is no fail-closed fallback available: the token this reader needs is `&`,
    the one thing a raw-text scan provably gets wrong, so a text-level fallback would refuse
    ordinary quoted arguments. A command whose quotes do not balance is also one no shell
    would run.
    """
    tokens = bashscan.tokenize(command)
    if tokens is None:
        return False, False
    # `prepare` is called separately for the heredocs alone. `tokenize` runs it internally on
    # the raw command, so the tokens already have comments stripped, line continuations
    # joined, and every unquoted newline rewritten to `;` -- which is what makes the
    # multi-line incident command read as the five separate commands it is.
    _text, heredocs = bashscan.prepare(command)
    backgrounds = _backgrounds_a_job(tokens)
    traps = _installs_an_exit_trap(tokens)
    if depth < _MAX_RECURSION_DEPTH:
        for program in _nested_programs(tokens, heredocs):
            nested_backgrounds, nested_traps = _scan(program, depth + 1)
            backgrounds = backgrounds or nested_backgrounds
            traps = traps or nested_traps
    return backgrounds, traps
