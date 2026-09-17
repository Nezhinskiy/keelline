#!/bin/sh
# Keelline hook wrapper. $1 = policy (open|closed); the rest is Keelline's own argv.
#
# This file exists because a Python process cannot fail closed about its own absence (D11):
# a missing script exits 2 by CPython accident, a missing interpreter 127, an ImportError 1,
# a lost executable bit 126 — and Claude Code reads every non-2 exit as a non-blocking error,
# which is permission. Each refusal prints its own token so an exit 2 is attributed, never
# inferred; Codex downgrades an exit 2 with empty stderr to a plain failure, so the reason is
# part of the contract and not a courtesy.
set -u

refuse() { echo "keelline: $1; refusing" >&2; exit 2; }
degrade() { echo "keelline: $1; continuing open" >&2; exit 0; }

# Before `set -u` can speak for us. An entry that lost its policy argument would otherwise die
# with the shell's own "unbound variable" and exit 1 — measured as exit 1 with no token on
# /bin/sh (bash 3.2.57), and exit 0 under `zsh --emulate sh`, so the mapping is not even
# portable. A disarmed guard must say so.
[ $# -ge 1 ] || refuse "KL_ARGV no policy argument"
policy="$1"
shift

fail() {
  if [ "$policy" = closed ]; then refuse "$1"; fi
  degrade "$1"
}

launcher="${CLAUDE_PLUGIN_ROOT:-}/scripts/keelline"

# The probe runs code rather than matching a path: bare `python3` in a hook subprocess can
# resolve to macOS's 3.9, and a path list alone would fall through to it on a machine with no
# python.org or Intel-Homebrew install (S8 row 2 measured exactly that fall-through).
p=
for c in ${KEELLINE_PYTHON_CANDIDATES:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3 python3}; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    p="$c"
    break
  fi
done
[ -n "$p" ] || fail "KL_NO_PY no python3 of 3.11 or newer among the candidates"

[ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "$launcher" ] || fail "KL_NO_LAUNCHER launcher missing at ${launcher}"

# Every entry but the dispatcher's relies on `--root` defaulting to the current directory, and
# no harness promises to launch a hook inside the project. Resolved here, once, rather than
# threaded through each entry's argv: CLAUDE_PROJECT_DIR is Claude Code's (Codex sets no such
# name — S1), and `git` answers for both. A root that cannot be resolved is not fatal: the
# command then finds no configuration and emits nothing, which is the correct open degradation.
root="${CLAUDE_PROJECT_DIR:-}"
[ -n "$root" ] || root=$(git rev-parse --show-toplevel 2>/dev/null || true)
[ -n "$root" ] && cd "$root" 2>/dev/null || true

"$p" "$launcher" "$@"
rc=$?
case "$rc" in
  0|2) exit "$rc" ;;
  *) fail "KL_RC keelline exited rc=$rc" ;;
esac
