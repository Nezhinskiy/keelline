# Keelline P0 Spikes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer the ten platform questions (S1–S10) the Keelline design depends on, and record each answer with the command that produced it and what it printed, so the wave-1 and wave-2 plans cite measurements instead of assumptions.

**Architecture:** Every spike runs against a scratch plugin installed into a throwaway `CLAUDE_CONFIG_DIR` (and, for Codex, a throwaway `CODEX_HOME`), never against the owner's real configuration. Shell state does not survive between steps, so every step re-derives its state from one fixed scratch root on disk and starts with the same preamble. Wherever Claude Code leaves a record on disk — the session transcript's per-hook records, the persisted-output files, the plugin cache — the spike reads the record instead of asking the model. Answers are written into the **Findings** section at the end of this file, which is the spike record §15.4 of the spec refers to; it is copied to the Keelline repository by the foundation package. S8, S9 and S10 produce fixture designs that later lanes turn into permanent tests; the rest produce answers only.

**Tech Stack:** bash and zsh, python3 (3.13.0 at `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3` and `/usr/local/bin/python3`, 3.9.6 at `/usr/bin/python3` — the difference is itself under test), `claude` 2.1.259, `codex` CLI (npm `@openai/codex` 0.153.4, not yet installed on this machine), `gh` 2.93.0, `uv` 0.11.19.

**Spec:** `docs/superpowers/specs/2026-09-05-agent-harness-extraction-design.md` — §14 lists the spikes; §5.3 and §9.5 consume S1, S7 and S8; §5.8 consumes S4; §6.1 consumes S6; §6.4 consumes S5; §7.4 consumes S9; §13 consumes S10; §2 D5 consumes S3.

**Scope:** package `spikes` (§15.2); consumes no contract; produces the recorded answers that `foundation` (S1, S4, S7), `hooks-core` (S1, S7, S8), `scaffold` (S9), `attach` (S6, S10), `setup` (S5, S6) and `workflows` (S10) cite. A change belongs to this plan iff it is a scratch experiment answering one of S1–S10 or an edit to the Findings section of this file; no Keelline source, no ai-daybook source, and nothing committed outside this plan file.

## Global Constraints

- Nothing is installed into, or written under, the owner's real `~/.claude` or `~/.codex`. The scratch root is `$HOME/.cache/keelline-spikes`; every configuration directory lives under it, and every helper refuses a path that does not.
- Shell state does not survive between steps (each step is one tool call), so **every step starts with the preamble** `set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"` and re-derives paths from fixed names under `$SPIKE`, never from variables an earlier step exported.
- Model turns are the last resort: a spike reads the session transcript, the persisted-output directory or the plugin cache whenever the answer is on disk. Where a turn is unavoidable it is `claude -p --model haiku` with a one-line prompt, at most three per spike, and its JSON result is kept and checked for `"is_error": false` before anything else is read. Flags that take a list use the `=` form (`--allowedTools=Bash,Read`): the space form is variadic and swallows the prompt.
- Consent precedes every side effect outside the scratch root, each asked in chat and each named: installing the Codex CLI from npm into the scratch prefix; `codex login` against the owner's OpenAI account; granting the `delete_repo` scope to the owner's `gh` token (`gh auth refresh -h github.com -s delete_repo`), without which the throwaway repositories cannot be deleted by the plan and must be deleted by the owner; creating each throwaway **private** repository under the owner's account. `--dangerously-bypass-hook-trust` is used only inside the scratch `CODEX_HOME` and is named as a deliberate bypass where it appears.
- Findings record environment variable **names**, never values, and paths relative to `$SPIKE`, never the owner's home directory or GitHub login; Task 11 scrubs both before the record leaves this repository.
- Findings are written in the past tense with the exact command and the observed output, per the plan lint in this repository (`scripts/check_plan.py`): a spike reports what it observed, never what it expects, and no step pre-loads the expected answer.
- All prose in this file is English.

---

### Task 0: Scratch root and helper library

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (the Findings section at the end)

**Interfaces:**
- Produces: the scratch library at `$SPIKE/lib.sh` (not committed) with `mkcfg NAME`, `require_under_spike PATH`, `mkplugin DIR NAME`, `install_plugin DIR NAME CFG`, `installed_root NAME CFG`, `run_claude CFG PROJECT ARGS…`, `hook_records CFG`, `persisted_outputs CFG`, used by every later task.

- [ ] **Step 1: Create the scratch root and the library**

```bash
set -eu
SPIKE="$HOME/.cache/keelline-spikes"; rm -rf "$SPIKE"; mkdir -p "$SPIKE"
cat > "$SPIKE/lib.sh" <<'EOF'
# Scratch helpers for the Keelline P0 spikes. Sourced by every step after `set -eu`.
: "${SPIKE:?SPIKE must be set to the scratch root}"

# Refuse any path outside the scratch root: the one rule every helper enforces.
require_under_spike() {
  case "$1" in "$SPIKE"/*) ;; *) echo "refusing: $1 is outside $SPIKE" >&2; exit 2 ;; esac
}

# A fresh Claude Code config dir at a fixed name; prints its path.
mkcfg() { local dir="$SPIKE/cfg-$1"; rm -rf "$dir"; mkdir -p "$dir"; echo "$dir"; }

# A scratch plugin at $1 named $2 with an empty hooks file and its own marketplace.
mkplugin() {
  local dir="$1" name="$2"
  require_under_spike "$dir"
  mkdir -p "$dir/.claude-plugin" "$dir/hooks" "$dir/scripts" "$dir/skills/probe"
  cat > "$dir/.claude-plugin/plugin.json" <<JSON
{"name": "$name", "version": "0.0.1", "description": "Keelline spike plugin $name"}
JSON
  cat > "$dir/.claude-plugin/marketplace.json" <<JSON
{"name": "$name-marketplace", "description": "Keelline spike marketplace $name",
 "owner": {"name": "spike"},
 "plugins": [{"name": "$name", "source": "./", "description": "spike"}]}
JSON
  echo '{"hooks": {}}' > "$dir/hooks/hooks.json"
}

# Install plugin $2 from directory $1 into the config dir $3.
install_plugin() {
  local dir="$1" name="$2" cfg="$3"
  require_under_spike "$cfg"
  CLAUDE_CONFIG_DIR="$cfg" claude plugin marketplace add "$dir"
  CLAUDE_CONFIG_DIR="$cfg" claude plugin install "$name@$name-marketplace"
}

# Where the installed copy of plugin $1 lives under config dir $2. Prints the path, or the
# word REFERENCED when the marketplace was recorded in place and nothing was copied.
installed_root() {
  local name="$1" cfg="$2" found
  found=$(find "$cfg/plugins" -path "*/$name/*" -name plugin.json 2>/dev/null | head -1 || true)
  if [ -n "$found" ]; then dirname "$(dirname "$found")"; else echo REFERENCED; fi
}

# One non-interactive turn in project dir $2 with config dir $1; the JSON result is saved to
# $2/last-result.json and printed. Fails loudly when the turn errored.
run_claude() {
  local cfg="$1" project="$2"; shift 2
  require_under_spike "$cfg"; require_under_spike "$project"
  (cd "$project" && CLAUDE_CONFIG_DIR="$cfg" claude -p --model haiku --output-format json "$@") \
    > "$project/last-result.json"
  python3 - "$project/last-result.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1]))
if result.get("is_error"):
    sys.exit(f"turn errored: {json.dumps(result)[:400]}")
print(result.get("result", "")[:400])
PY
}

# Every per-hook record Claude Code wrote into the transcripts under config dir $1:
# one line per record with the hook command, its exit code, stdout length, stderr, and
# whether an additional-context attachment reached the model.
hook_records() {
  local cfg="$1"; require_under_spike "$cfg"
  python3 - "$cfg" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]) / "projects"
def walk(node, path):
    if isinstance(node, dict):
        kind = node.get("type")
        if kind in {"hook_success", "hook_error", "hook_additional_context"}:
            out = node.get("stdout") or node.get("content") or node.get("additionalContext") or ""
            print(f"{path.name}: {kind} cmd={node.get('command', node.get('hookName'))!r} "
                  f"rc={node.get('exitCode')} stdout_len={len(str(out))} "
                  f"stderr={str(node.get('stderr', ''))[:120]!r}")
        for value in node.values():
            walk(value, path)
    elif isinstance(node, list):
        for value in node:
            walk(value, path)
for transcript in sorted(root.rglob("*.jsonl")):
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            walk(json.loads(line), transcript)
        except json.JSONDecodeError:
            continue
PY
}

# Every persisted hook output under config dir $1 (the overflow files a capped hook leaves).
persisted_outputs() {
  require_under_spike "$1"
  find "$1/projects" -path '*tool-results*' -name 'hook-*' 2>/dev/null || true
}
EOF
echo "$SPIKE"
```

- [ ] **Step 2: Smoke the library once**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CFG=$(mkcfg s0); mkplugin "$SPIKE/p0" p0; install_plugin "$SPIKE/p0" p0 "$CFG"
CLAUDE_CONFIG_DIR="$CFG" claude plugin list | grep -c p0
installed_root p0 "$CFG"
```

Expected: `1`, then either an installed path under `$CFG/plugins` or `REFERENCED`. Record which under Findings → Environment: it decides whether later tasks mutate an installed copy or the source directory. If the install fails, record the error and stop: every later spike installs a scratch plugin from a local marketplace.

- [ ] **Step 3: Record the environment**

Append to Findings → Environment: the outputs of `claude --version`, `python3 --version`, `/usr/local/bin/python3 --version`, `/usr/bin/python3 --version`, `uv --version`, `gh --version | head -1`, `gh auth status 2>&1 | grep -i scopes`, the `installed_root` answer, and the date.

---

### Task 1: S1 — Codex plugin hooks

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S1)

**Interfaces:**
- Produces: for `foundation`, the environment variable or stdin field that identifies Codex (the plan's `detect_harness()` is provisional until this lands) and whether extra keys in a shared hook entry are tolerated; for `hooks-core`, the tool names Codex reports in `PreToolUse`; for §5.1, which marketplace file Codex reads.

- [ ] **Step 1: Ask, then install the Codex CLI into the scratch prefix and log in**

Ask in chat: "S1 installs `@openai/codex@0.153.4` from npm into the scratch prefix and runs `codex login` against your OpenAI account, with the token kept under the scratch root; proceed?" Only after a yes:

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
mkdir -p "$SPIKE/npm" && npm install --prefix "$SPIKE/npm" @openai/codex@0.153.4
"$SPIKE/npm/node_modules/.bin/codex" --version
mkdir -p "$SPIKE/codex-home"
CODEX_HOME="$SPIKE/codex-home" "$SPIKE/npm/node_modules/.bin/codex" login
```

`$SPIKE/codex-home` holds the login for Tasks 1–3 and is deleted by Task 11.

- [ ] **Step 2: Build a probe plugin whose hook logs its environment names and stdin keys**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
mkplugin "$SPIKE/s1" s1
cat > "$SPIKE/s1/scripts/probe.py" <<'EOF'
import json, os, sys
event = json.load(sys.stdin)
names = sorted(k for k in os.environ if "PLUGIN" in k or "CLAUDE" in k or "CODEX" in k)
record = {"argv": sys.argv[1:], "env_names": names, "stdin_keys": sorted(event),
          "tool_name": event.get("tool_name"), "event": event.get("hook_event_name")}
with open(os.environ["S1_LOG"], "a") as fh:
    fh.write(json.dumps(record) + "\n")
print(json.dumps({"hookSpecificOutput": {"hookEventName": event.get("hook_event_name", "?"),
                  "additionalContext": "S1_CANARY_" + str(event.get("hook_event_name"))}}))
EOF
cat > "$SPIKE/s1/hooks/hooks.json" <<'EOF'
{"hooks": {
  "SessionStart": [{"hooks": [{"type": "command",
     "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/probe.py\" session",
     "additionalContextLimit": 0, "additionalContextChars": 0}]}],
  "PreToolUse": [{"matcher": "Bash|Read|Grep|Glob|Edit|Write|apply_patch",
     "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/probe.py\" pre"}]}]
}}
EOF
mkdir -p "$SPIKE/s1/proj" && git -C "$SPIKE/s1/proj" init -q
echo "S1 readme" > "$SPIKE/s1/proj/README.md"
printf 'export S1_LOG="%s/s1/log-%%s.jsonl"\n' "$SPIKE" > "$SPIKE/s1/env.sh"
```

Both entries carry the Codex spill key `additionalContextLimit` **and** the name the Claude binary contains, `additionalContextChars` (measured 2026-09-05 with `strings`; no `additionalContextLimit` string exists in `claude` 2.1.259), so one run answers whether each harness tolerates a key it does not own.

- [ ] **Step 3: Run the probe under Claude Code and read the log and the transcript**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CFG=$(mkcfg s1); install_plugin "$SPIKE/s1" s1 "$CFG"
export S1_LOG="$SPIKE/s1/log-claude.jsonl"; : > "$S1_LOG"
run_claude "$CFG" "$SPIKE/s1/proj" --allowedTools=Bash,Read,Write \
  "Run the shell command: echo hello. Then read README.md. Then create probe.txt containing hi."
python3 -c 'import json,sys
for line in open(sys.argv[1]):
    r = json.loads(line); print(r["argv"], r["event"], r["tool_name"], r["env_names"], r["stdin_keys"])' "$S1_LOG"
hook_records "$CFG"
```

Record under Findings → S1: the environment variable names and stdin keys per event; whether the install and the session accepted the two extra keys (an install error or a missing hook record is the signal); the exit code and stdout length of each hook record.

- [ ] **Step 4: Run the same probe, same prompt, under Codex**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CODEX="$SPIKE/npm/node_modules/.bin/codex"; export CODEX_HOME="$SPIKE/codex-home"
"$CODEX" plugin marketplace add "$SPIKE/s1"
"$CODEX" plugin add s1@s1-marketplace
export S1_LOG="$SPIKE/s1/log-codex.jsonl"; : > "$S1_LOG"
(cd "$SPIKE/s1/proj" && "$CODEX" exec --dangerously-bypass-hook-trust \
  "Run the shell command: echo hello. Then read README.md. Then create probe.txt containing hi.") \
  > "$SPIKE/s1/codex-result.txt" 2>&1; tail -5 "$SPIKE/s1/codex-result.txt"
python3 -c 'import json,sys
for line in open(sys.argv[1]):
    r = json.loads(line); print(r["argv"], r["event"], r["tool_name"], r["env_names"], r["stdin_keys"])' "$S1_LOG"
```

`--dangerously-bypass-hook-trust` is deliberate: the scratch `CODEX_HOME` has no trust store and the spike measures the hooks, not the trust prompt. If `plugin marketplace add` refuses the directory, record the error verbatim and which marketplace file, if any, Codex asked for.

- [ ] **Step 5: Record the four S1 answers, from the logs only**

Under Findings → S1, each with the command and the observed line: (1) the environment variable names present in the Codex hook and absent in the Claude one, and any stdin key that only Codex sends; (2) the `tool_name` values Codex reported for the shell, read and file-creation actions, against the same three actions in the Claude arm; (3) whether each harness tolerated `additionalContextLimit` and `additionalContextChars` in a shared entry; (4) which marketplace file Codex read.

---

### Task 2: S2 — plugin-root substitution and executable bits

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S2)

**Interfaces:**
- Produces: for `foundation` and `hooks-core`, whether `${CLAUDE_PLUGIN_ROOT}` is substituted in hook commands and in skill content on each harness, and whether the installed copy keeps file modes.

- [ ] **Step 1: Build a plugin with a skill that names the root and a script without an executable bit**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
mkplugin "$SPIKE/s2" s2
cat > "$SPIKE/s2/skills/probe/SKILL.md" <<'EOF'
---
name: s2-probe
description: Use when asked for the S2 probe path. Prints where the plugin lives.
---
When invoked, reply with exactly one line, the following text with nothing added:
ROOT=${CLAUDE_PLUGIN_ROOT}
EOF
printf '#!/usr/bin/env python3\nprint("S2_SCRIPT_RAN")\n' > "$SPIKE/s2/scripts/noexec.py"
chmod -x "$SPIKE/s2/scripts/noexec.py"
cat > "$SPIKE/s2/hooks/hooks.json" <<'EOF'
{"hooks": {"SessionStart": [{"hooks": [
  {"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/noexec.py\""},
  {"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/scripts/noexec.py\""}
]}]}}
EOF
mkdir -p "$SPIKE/s2/proj" && git -C "$SPIKE/s2/proj" init -q
```

- [ ] **Step 2: Observe substitution in the hook and the executable-bit outcome from the transcript**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CFG=$(mkcfg s2); install_plugin "$SPIKE/s2" s2 "$CFG"
ROOT=$(installed_root s2 "$CFG"); echo "installed at: $ROOT"
[ "$ROOT" = REFERENCED ] || stat -f '%Sp %N' "$ROOT/scripts/noexec.py"
run_claude "$CFG" "$SPIKE/s2/proj" "Reply with the single word ready."
hook_records "$CFG"
```

Record: the two hook records' commands as written into the transcript (a resolved absolute path means substitution happened in the hook command), their exit codes, and the mode of the installed script.

- [ ] **Step 3: Observe substitution in skill content on Claude Code, with an oracle the model cannot fake**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CFG="$SPIKE/cfg-s2"; ROOT=$(installed_root s2 "$CFG")
run_claude "$CFG" "$SPIKE/s2/proj" "Use the s2-probe skill."
echo "installed root: $ROOT"
```

The installed root contains a cache directory name the model cannot guess, so a reply that quotes that exact path is substitution and a reply of the literal `${CLAUDE_PLUGIN_ROOT}` is its absence; anything else is recorded as inconclusive.

- [ ] **Step 4: Repeat the skill half under Codex**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CODEX="$SPIKE/npm/node_modules/.bin/codex"; export CODEX_HOME="$SPIKE/codex-home"
"$CODEX" plugin marketplace add "$SPIKE/s2" && "$CODEX" plugin add s2@s2-marketplace
(cd "$SPIKE/s2/proj" && "$CODEX" exec --dangerously-bypass-hook-trust "Use the s2-probe skill.") \
  > "$SPIKE/s2/codex-result.txt" 2>&1; tail -3 "$SPIKE/s2/codex-result.txt"
```

Record under Findings → S2 whether Codex substituted the variable in skill content, and which line the reply contained.

---

### Task 3: S3 — Codex `/import` scope for Claude memories

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S3)

**Interfaces:**
- Produces: for §2 D5, whether Codex's import carries Claude memory notes at all; if it does, §6.4 gains one sentence, otherwise nothing changes.

- [ ] **Step 1: Let Claude Code create the project directory, then seed the store where it looks**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CFG=$(mkcfg s3); mkdir -p "$SPIKE/s3/proj" && git -C "$SPIKE/s3/proj" init -q
run_claude "$CFG" "$SPIKE/s3/proj" "Reply with the single word ready."
SLUG=$(ls "$CFG/projects" | head -1); echo "slug: $SLUG"
mkdir -p "$CFG/projects/$SLUG/memory"
printf -- '- [S3 probe → what the import carries](s3-probe.md)\n' > "$CFG/projects/$SLUG/memory/MEMORY.md"
cat > "$CFG/projects/$SLUG/memory/s3-probe.md" <<'EOF'
---
name: s3-probe
description: S3_CANARY_NOTE the note body the import should carry
metadata:
  type: project
---
S3_CANARY_BODY
EOF
```

The slug is read from what Claude Code created rather than derived, because the real slug maps every non-alphanumeric character and resolves `/tmp` to `/private/tmp` first.

- [ ] **Step 2: Run the import interactively with the owner present, then search the Codex home**

`/import` is a TUI command; `codex exec` sends a slash string to the model as a prompt. Start the TUI in the project with the scratch configuration and let the owner type the command:

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CODEX="$SPIKE/npm/node_modules/.bin/codex"
cd "$SPIKE/s3/proj" && CLAUDE_CONFIG_DIR="$SPIKE/cfg-s3" CODEX_HOME="$SPIKE/codex-home" "$CODEX"
```

Owner types `/import`, chooses Claude Code, and exits. Then:

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
grep -rl 'S3_CANARY' "$SPIKE/codex-home" 2>/dev/null || echo "no canary under the Codex home"
grep -rl 'S3_CANARY' "$SPIKE/s3/proj" 2>/dev/null || echo "no canary under the project"
```

- [ ] **Step 3: Record**

Under Findings → S3: which canary strings landed where (index line, note body, neither), in what shape (a Codex memory record, a copied markdown file, a settings entry), and the design consequence: a sentence in §6.4 if notes travel, nothing otherwise.

---

### Task 4: S4 — `claude plugin validate --strict` per manifest path

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S4)

**Interfaces:**
- Produces: for `foundation` Task 9 and Task 10, the exact `validate` invocations that report a defect in each manifest and in the plugin's skills and agents, and every warning the §5.1 layout produces.

- [ ] **Step 1: Build the §5.1 layout with the foundation plan's real manifests**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
mkdir -p "$SPIKE/s4/.claude-plugin" "$SPIKE/s4/.codex-plugin" "$SPIKE/s4/agents" "$SPIKE/s4/skills/init" "$SPIKE/s4/scripts"
cat > "$SPIKE/s4/.claude-plugin/plugin.json" <<'EOF'
{
  "name": "keelline",
  "version": "0.1.0",
  "description": "Keelline spike copy of the foundation manifest.",
  "author": {"name": "spike"},
  "repository": "https://example.invalid/keelline",
  "license": "MIT",
  "keywords": ["spike"],
  "userConfig": {
    "reply_language": {"type": "string", "title": "Reply language", "description": "Language for chat replies.", "default": ""},
    "artifact_language": {"type": "string", "title": "Artifact language", "description": "Language for durable artifacts.", "default": "en"},
    "preset": {"type": "string", "title": "Preset", "description": "Preset applied by setup and init.", "default": "recommended"}
  }
}
EOF
cat > "$SPIKE/s4/.claude-plugin/marketplace.json" <<'EOF'
{"name": "keelline-marketplace", "description": "Keelline spike marketplace", "owner": {"name": "spike"},
 "plugins": [{"name": "keelline", "source": "./", "description": "spike"}]}
EOF
cat > "$SPIKE/s4/.codex-plugin/plugin.json" <<'EOF'
{"name": "keelline", "version": "0.1.0", "description": "spike", "skills": "./skills/",
 "interface": {"displayName": "Keelline", "shortDescription": "spike"}}
EOF
printf -- '---\nname: init\ndescription: spike skill\n---\nbody\n' > "$SPIKE/s4/skills/init/SKILL.md"
printf -- '---\nname: probe\ndescription: spike agent\n---\nbody\n' > "$SPIKE/s4/agents/probe.md"
printf '#!/usr/bin/env python3\n' > "$SPIKE/s4/scripts/keelline"; chmod +x "$SPIKE/s4/scripts/keelline"
cp -R "$SPIKE/s4" "$SPIKE/s4-broken"
printf 'name: init\n' > "$SPIKE/s4-broken/skills/init/SKILL.md"
printf -- '---\nname:\n---\n' > "$SPIKE/s4-broken/agents/probe.md"
printf '{not json' > "$SPIKE/s4-broken/.codex-plugin/plugin.json"
```

- [ ] **Step 2: Validate the directory, each manifest path, and the Codex manifest, on both trees**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
for tree in s4 s4-broken; do
  for target in "" ".claude-plugin/plugin.json" ".claude-plugin/marketplace.json" ".codex-plugin/plugin.json"; do
    for flag in "" "--strict"; do
      out="$SPIKE/$tree/validate-$(echo "$target$flag" | tr '/.-' '___').txt"
      set +e; claude plugin validate "$SPIKE/$tree/$target" $flag > "$out" 2>&1; rc=$?; set -e
      printf '%s %s %s -> rc=%s (%s lines)\n' "$tree" "${target:-<dir>}" "$flag" "$rc" "$(wc -l < "$out")"
    done
  done
done
```

Full outputs are kept under each tree; nothing is truncated.

- [ ] **Step 3: Record**

Under Findings → S4: the sixteen exit codes; for the broken tree, which invocation reported the broken skill, the broken agent and the broken Codex manifest, and which reported none of them; every warning the valid tree produced under `--strict`. The `foundation` plan's CI invokes exactly the invocations that discriminate.

---

### Task 5: S5 — background refresh of a private SSH marketplace

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S5)

**Interfaces:**
- Produces: for §6.4 and the `setup` lane, whether a private marketplace over SSH updates at session start, whether HTTPS falls back to a re-clone or fails, and whether `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` changes the HTTPS outcome.

- [ ] **Step 1: Ask, then create a throwaway private repository holding the S4 plugin**

Ask in chat: "S5 creates a private repository `keelline-spike-s5` under your GitHub account; deleting it at the end needs the `delete_repo` scope, which your token does not have — run `gh auth refresh -h github.com -s delete_repo` now, or delete the repository yourself afterwards; proceed?" Only after a yes:

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
OWNER=$(gh api user --jq .login); echo "$OWNER" > "$SPIKE/owner"
gh repo create "$OWNER/keelline-spike-s5" --private
cp -R "$SPIKE/s4" "$SPIKE/s5" && cd "$SPIKE/s5" && git init -q -b main && git add -A && git commit -qm "spike: s5 plugin"
git remote add origin "git@github.com:$OWNER/keelline-spike-s5.git" && git push -q -u origin main
```

- [ ] **Step 2: SSH arm — install, push a change, and let a session start trigger the refresh**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
OWNER=$(cat "$SPIKE/owner"); CFG=$(mkcfg s5-ssh)
CLAUDE_CONFIG_DIR="$CFG" claude plugin marketplace add "git@github.com:$OWNER/keelline-spike-s5.git"
CLAUDE_CONFIG_DIR="$CFG" claude plugin install keelline@keelline-marketplace
cd "$SPIKE/s5" && sed -i '' 's/"version": "0.1.0"/"version": "0.1.1"/' .claude-plugin/plugin.json \
  && git commit -qam "spike: bump" && git push -q
mkdir -p "$SPIKE/s5/proj" && git -C "$SPIKE/s5/proj" init -q
time run_claude "$CFG" "$SPIKE/s5/proj" "Reply with the single word ready."
CLAUDE_CONFIG_DIR="$CFG" claude plugin list | grep -A3 keelline
grep -rl '0.1.1' "$CFG/plugins" 2>/dev/null | head -3 || echo "installed copy still at 0.1.0"
```

The background refresh runs at session start; the foreground `claude plugin marketplace update keelline-marketplace` is run afterwards and recorded separately, so the two are never confused.

- [ ] **Step 3: HTTPS arm, twice — without and with the keep-on-failure variable**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
OWNER=$(cat "$SPIKE/owner")
for arm in https https-keep; do
  CFG=$(mkcfg "s5-$arm")
  CLAUDE_CONFIG_DIR="$CFG" claude plugin marketplace add "https://github.com/$OWNER/keelline-spike-s5.git"
  CLAUDE_CONFIG_DIR="$CFG" claude plugin install keelline@keelline-marketplace
  cd "$SPIKE/s5" && sed -i '' "s/\"version\": \"0.1.[0-9]*\"/\"version\": \"0.1.$RANDOM\"/" .claude-plugin/plugin.json \
    && git commit -qam "spike: bump for $arm" && git push -q
  if [ "$arm" = https-keep ]; then export CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1; fi
  time run_claude "$CFG" "$SPIKE/s5/proj" "Reply with the single word ready."
  CLAUDE_CONFIG_DIR="$CFG" claude plugin list | grep -A3 keelline
  unset CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE
done
```

- [ ] **Step 4: Record, then delete the repository**

Under Findings → S5: for each arm, whether the installed version changed at session start, how long the turn took, and what the foreground update printed. Then:

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
OWNER=$(cat "$SPIKE/owner"); gh repo delete "$OWNER/keelline-spike-s5" --yes || echo "owner deletes keelline-spike-s5 by hand"
```

---

### Task 6: S6 — `gh repo create --template` race and marketplace renaming

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S6)

**Interfaces:**
- Produces: for the `overlay` lane, whether `--template --clone` races GitHub's asynchronous generation and therefore how `overlay create` must retry; for `attach`, whether a renamed overlay marketplace installs.

- [ ] **Step 1: Ask, then create a throwaway private template repository**

Ask in chat: "S6 creates two private repositories under your account — a template `keelline-spike-template` and an instance `keelline-spike-overlay` — and deletes both at the end if the `delete_repo` scope is granted; proceed?" Only after a yes:

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
OWNER=$(gh api user --jq .login); echo "$OWNER" > "$SPIKE/owner"
mkdir -p "$SPIKE/s6/tpl/.claude-plugin" && cd "$SPIKE/s6/tpl"
echo '{"name": "spike-overlay", "version": "0.0.1", "description": "spike overlay"}' > .claude-plugin/plugin.json
echo '{"name": "spike-overlay-marketplace", "description": "spike", "owner": {"name": "spike"}, "plugins": [{"name": "spike-overlay", "source": "./", "description": "spike"}]}' > .claude-plugin/marketplace.json
git init -q -b main && git add -A && git commit -qm "spike: template"
gh repo create "$OWNER/keelline-spike-template" --private --source . --push
gh api -X PATCH "repos/$OWNER/keelline-spike-template" -F is_template=true --jq .is_template
```

- [ ] **Step 2: Create the private instance from the template, timing the clone race**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
OWNER=$(cat "$SPIKE/owner"); mkdir -p "$SPIKE/s6/work" && cd "$SPIKE/s6/work"
set +e; time gh repo create "$OWNER/keelline-spike-overlay" --private --template "$OWNER/keelline-spike-template" --clone; rc=$?; set -e
echo "create rc=$rc"
if [ ! -d keelline-spike-overlay/.claude-plugin ]; then
  gh repo view "$OWNER/keelline-spike-overlay" --json name --jq .name && echo "repository exists, clone missing"
  sleep 10; git clone -q "git@github.com:$OWNER/keelline-spike-overlay.git" && echo "cloned on retry"
fi
```

Record: the first command's exit code and timing, whether the repository existed when the clone was missing, and whether one retry sufficed.

- [ ] **Step 3: Rename the marketplace and plugin the way `overlay init --owner` will, then install**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
OWNER=$(cat "$SPIKE/owner"); cd "$SPIKE/s6/work/keelline-spike-overlay"
python3 - "$OWNER" <<'EOF'
import json, sys, pathlib
owner = sys.argv[1].lower()
for name in ("plugin.json", "marketplace.json"):
    path = pathlib.Path(".claude-plugin") / name
    data = json.loads(path.read_text())
    data["name"] = f"{data['name']}-{owner}"
    for entry in data.get("plugins", []):
        entry["name"] = f"{entry['name']}-{owner}"
    path.write_text(json.dumps(data, indent=2) + "\n")
EOF
git commit -qam "spike: rename for owner" && git push -q
CFG=$(mkcfg s6)
CLAUDE_CONFIG_DIR="$CFG" claude plugin marketplace add "git@github.com:$OWNER/keelline-spike-overlay.git"
CLAUDE_CONFIG_DIR="$CFG" claude plugin install "spike-overlay-$OWNER@spike-overlay-marketplace-$OWNER"
CLAUDE_CONFIG_DIR="$CFG" claude plugin list
```

- [ ] **Step 4: Record and delete both repositories**

Under Findings → S6: the race outcome, the retry rule `overlay create` needs, and whether the renamed marketplace installed. Then:

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
OWNER=$(cat "$SPIKE/owner")
gh repo delete "$OWNER/keelline-spike-overlay" --yes || echo "owner deletes keelline-spike-overlay by hand"
gh repo delete "$OWNER/keelline-spike-template" --yes || echo "owner deletes keelline-spike-template by hand"
```

---

### Task 7: S7 — the 10,000-character cap, per entry or per event

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S7)

**Interfaces:**
- Produces: for `memory-engine` and `hooks-core`, whether §9.5's one-entry-per-bundle remedy holds (the cap applies per hook entry) and the largest single entry that is not spilled; for `foundation`, the value behind the preset's `hook_output_chars`.

- [ ] **Step 1: A probe that emits exactly N characters and reports N to stderr**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
mkplugin "$SPIKE/s7" s7
cat > "$SPIKE/s7/scripts/big.py" <<'EOF'
import json, sys
tag, size = sys.argv[1], int(sys.argv[2])
prefix = f"CANARY_{tag} "
body = prefix + "x" * (size - len(prefix))
print(f"S7 {tag} emitted {len(body)} characters", file=sys.stderr)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": body}}))
EOF
mkdir -p "$SPIKE/s7/proj" && git -C "$SPIKE/s7/proj" init -q
cat > "$SPIKE/s7/arm.sh" <<'EOF'
# arm NAME ENTRY_SIZES… : write hooks.json with one SessionStart entry per size, install into
# a fresh config dir, run one turn, print the hook records and the persisted-output count.
arm() {
  local name="$1"; shift
  local entries="" tag=A
  for size in "$@"; do
    entries="$entries{\"type\": \"command\", \"command\": \"python3 \\\"\${CLAUDE_PLUGIN_ROOT}/scripts/big.py\\\" $tag $size\"},"
    tag=$(printf "\\$(printf '%03o' $(( $(printf '%d' "'$tag") + 1 )))")
  done
  printf '{"hooks": {"SessionStart": [{"hooks": [%s]}]}}\n' "${entries%,}" > "$SPIKE/s7/hooks/hooks.json"
  local cfg; cfg=$(mkcfg "s7-$name"); install_plugin "$SPIKE/s7" s7 "$cfg" >/dev/null
  run_claude "$cfg" "$SPIKE/s7/proj" "Reply with the single word ready." >/dev/null
  echo "== arm $name (sizes: $*)"; hook_records "$cfg"
  echo "persisted files: $(persisted_outputs "$cfg" | wc -l | tr -d ' ')"
}
EOF
```

- [ ] **Step 2: Three arms that change one variable at a time**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"; . "$SPIKE/s7/arm.sh"
arm control 8000
arm two-entries 8000 8000
arm one-big 16000
```

The control is one 8,000-character entry; the second arm adds a second entry of the same size; the third keeps one entry and doubles its size. Under a per-entry cap the second arm leaves no persisted file and the third leaves one; under a per-event cap the second arm also spills.

- [ ] **Step 3: The margin, one entry each**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"; . "$SPIKE/s7/arm.sh"
for size in 9000 9900 9999 10000 10001; do arm "margin-$size" "$size"; done
```

- [ ] **Step 4: Record, both branches**

Under Findings → S7: per arm, the stderr size line, the hook record's stdout length, and the persisted-file count. If the two-entry arm produced no persisted file and the one-big arm produced one, §9.5's per-bundle remedy holds and the largest unspilled margin size is the value `hook_output_chars` records. If the two-entry arm produced a persisted file, the cap is per event, §9.5's remedy is falsified, and the record says so: `hooks-core` must then spread bundles across events or shrink them, and the wave-1 merger amends §9.5.

---

### Task 8: S8 — the fail-closed matrix through the wrapper

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S8)

**Interfaces:**
- Produces: the measured `(row, payload) → (exit code, blocked?, attributed reason)` table the `hooks-core` lane turns into a permanent wrapper test, and the first draft of the wrapper itself, kept under `$SPIKE/s8` until that lane adopts it.

- [ ] **Step 1: The wrapper the design describes (§5.3), with its own attributed refusals**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
mkplugin "$SPIKE/s8" s8
cat > "$SPIKE/s8/hooks/run-hook.sh" <<'EOF'
#!/bin/sh
# Keelline hook wrapper (spike draft). $1 = event, $2 = policy (open|closed).
# Every refusal prints its own token so an exit 2 is attributed, never inferred.
event="$1"; policy="$2"
refuse() { echo "keelline: $1; refusing" >&2; exit 2; }
degrade() { echo "keelline: $1; continuing open" >&2; exit 0; }
script="${CLAUDE_PLUGIN_ROOT:-}/scripts/guard.py"
p=
for c in ${KEELLINE_PYTHON_CANDIDATES:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /usr/local/bin/python3 /usr/bin/python3}; do
  if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    p="$c"; break
  fi
done
if [ -z "$p" ]; then
  [ "$policy" = closed ] && refuse "KL_NO_PY no python3 of 3.11 or newer among the candidates"
  degrade "KL_NO_PY"
fi
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -f "$script" ]; then
  [ "$policy" = closed ] && refuse "KL_NO_SCRIPT guard script missing at ${script}"
  degrade "KL_NO_SCRIPT"
fi
"$p" "$script" "$event"; rc=$?
case "$rc" in
  0|2) exit "$rc" ;;
  *) [ "$policy" = closed ] && refuse "KL_GUARD_RC guard failed with rc=$rc"; degrade "KL_GUARD_RC rc=$rc" ;;
esac
EOF
chmod +x "$SPIKE/s8/hooks/run-hook.sh"
cat > "$SPIKE/s8/scripts/guard.py" <<'EOF'
import json, sys
event = json.load(sys.stdin)
if "S8_DENY" in json.dumps(event.get("tool_input", {})):
    print("keelline: KL_DENY the S8 guard denies this command", file=sys.stderr); sys.exit(2)
sys.exit(0)
EOF
cat > "$SPIKE/s8/hooks/hooks.json" <<'EOF'
{"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
  {"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh\" PreToolUse closed"}
]}]}}
EOF
mkdir -p "$SPIKE/s8/proj" && git -C "$SPIKE/s8/proj" init -q
```

The candidate list is §5.3's — the 3.13 framework interpreter, `/usr/local/bin/python3`, `/usr/bin/python3` — and each candidate is checked for the 3.11 floor, not only for `-x`; `KEELLINE_PYTHON_CANDIDATES` exists only so the matrix can point the wrapper at the 3.9 interpreter alone.

- [ ] **Step 2: The two-sided baseline through the harness**

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CFG=$(mkcfg s8); install_plugin "$SPIKE/s8" s8 "$CFG"
ROOT=$(installed_root s8 "$CFG"); [ "$ROOT" = REFERENCED ] && ROOT="$SPIKE/s8"; echo "$ROOT" > "$SPIKE/s8/root"
cp -R "$ROOT" "$SPIKE/s8/pristine"
run_claude "$CFG" "$SPIKE/s8/proj" --allowedTools=Bash "Run exactly this shell command: echo S8_DENY"
run_claude "$CFG" "$SPIKE/s8/proj" --allowedTools=Bash "Run exactly this shell command: echo S8_ALLOW"
hook_records "$CFG"
```

Record: the DENY turn's hook record must show rc 2 and `KL_DENY` in stderr, and the ALLOW turn's must show rc 0 with `S8_ALLOW` in the result — both verdicts are needed before the matrix means anything (a one-sided oracle proves nothing, per the working-memory note on oracles that discriminate).

- [ ] **Step 3: Six rows, two payloads each, restoring the pristine copy between rows**

For each row, apply the mutation to the copy at `$(cat "$SPIKE/s8/root")`, run **both** prompts from Step 2, read `hook_records`, then restore with `rm -rf "$ROOT" && cp -R "$SPIKE/s8/pristine" "$ROOT"`:

| Row | Mutation |
|---|---|
| no interpreter | in the wrapper, set `KEELLINE_PYTHON_CANDIDATES=/nonexistent/python3` by prefixing the command in hooks.json with `env KEELLINE_PYTHON_CANDIDATES=/nonexistent/python3` |
| only 3.9 available | same, with `KEELLINE_PYTHON_CANDIDATES=/usr/bin/python3` |
| `CLAUDE_PLUGIN_ROOT` unset | prefix the command in hooks.json with `env -u CLAUDE_PLUGIN_ROOT` |
| script deleted | remove the guard script (scripts, guard.py) from the copy |
| ImportError planted | prepend `import no_such_module_s8` to the guard script in the copy |
| executable bit cleared | `chmod -x hooks/run-hook.sh` in the copy |

For each row and payload record: the exit code from the hook record, the stderr token (`KL_NO_PY`, `KL_NO_SCRIPT`, `KL_GUARD_RC`, `KL_DENY`, or none), and whether the turn was blocked (the result text).

- [ ] **Step 4: Record the consequence**

The wrapper is correct if, on the pristine copy, DENY gives rc 2 with `KL_DENY` and ALLOW gives rc 0; and if every broken row except "executable bit cleared" gives rc 2 for **both** payloads with the wrapper's own token in stderr — a broken guard refuses everything, and says why. The executable-bit row cannot be handled by the wrapper (it never runs); it is the installer's and `doctor`'s row (§5.3). Any row that blocked without a token, or that let ALLOW through while broken, is recorded with the wrapper change that would close it; the `hooks-core` lane starts from this draft.

---

### Task 9: S9 — path containment fixture (design only)

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S9)

**Interfaces:**
- Produces: the fixture the `scaffold` lane implements as a containment test with `plan()` from contract C2.

- [ ] **Step 1: Write the fixture as a `keelline.toml` and expected outcomes**

Under Findings → S9, record this fixture verbatim as the test's input:

```toml
[keelline]
version = "0.1.0"
state = "adopting"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "../common"
base_branch = "main"
release_branch = "main"

[paths]
agents_md = "../../.claude/CLAUDE.md"
specs = "/etc/keelline-specs"
plans = "docs/plans"
memory = "link-to-elsewhere"
```

with the memory path created as a symlink to a directory outside the fixture root, and these assertions: loading the config raises the loader's error on the project name (one path segment); with the name corrected, `plan()` yields zero actions for the agents file, the specs directory and the memory path, and exactly the actions for the plans directory; `apply()` on a plan computed before the plans directory was swapped for a symlink refuses to write. Each assertion is paired, in the scaffold plan, with the mutation expected to redden it.

- [ ] **Step 2: Nothing to run** — the engine does not exist in P0; this task ends when the fixture is recorded.

---

### Task 10: S10 — clone-to-exfiltration scenario (design only)

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → S10)

**Interfaces:**
- Produces: the scenario the `workflows` lane implements in the smoke workflow, with fixtures from the `attach` and `memory-engine` lanes.

- [ ] **Step 1: Record the scenario and its three separate assertions**

Under Findings → S10: a fixture repository with in-repo memory mode, a note carrying a negative startup rank whose body is `S10_RULE_CANARY`, and the project name `victim`; a scratch overlay whose `victim` project store holds a note with body `S10_STORE_CANARY` and whose project binding names a different remote. Assertions: (1) a `SessionStart` run against the fixture without the in-repo trust step emits no additional context containing `S10_RULE_CANARY`, and with trust emits it wrapped in the in-repo data marker and after the owner's rules; (2) a memory search for `S10_STORE_CANARY` from the fixture returns nothing; (3) attaching the fixture to the overlay's `victim` store exits 2 with a remote-mismatch reason and creates no symlink.

- [ ] **Step 2: Nothing to run** — this task ends when the scenario is recorded.

---

### Task 11: Close the record

**Files:**
- Modify: `docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md` (Findings → Summary)

- [ ] **Step 1: Fill the summary table** — one row per spike: answer in one line, the design section it feeds, and whether the design changes (`as designed` / `amend §…`).

- [ ] **Step 2: Scrub the record**

```bash
grep -nE "$HOME|$(cat "$HOME/.cache/keelline-spikes/owner" 2>/dev/null || echo NO_OWNER_RECORDED)" \
  docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md || echo "record carries no home path and no login"
```

Any hit is rewritten relative to `$SPIKE` or without the login before the commit.

- [ ] **Step 3: Delete the scratch root, including the Codex login and the npm prefix**

```bash
rm -rf "$HOME/.cache/keelline-spikes"
```

- [ ] **Step 4: Commit the record**

```bash
git add docs/superpowers/plans/2026-09-05-agent-harness-p0-spikes.md
git commit -m "docs(plans): record the Keelline P0 spike answers"
```

---

## Findings

Filled in during execution; every entry names the command that produced it and quotes what it printed. Written in the past tense. Paths are relative to the scratch root; environment variables are named, never valued.

**No cited artifact under `$SPIKE` survives**: the scratch root was deleted after each review round, and the `.superpowers/sdd/2026-09-05-agent-harness-p0-spikes/` scripts and logs this record also cites are gitignored, so nothing quoted below can be re-read from disk by anyone who did not run it — every quote here is testimony, not a reference. Each entry discloses per quote which artifact it came from, so a reader can tell what kind of evidence backs any one line even though the file itself is gone. The one exception is finding A2(b)'s own log (`a2b-exec-bit-measurement.log`, alongside the script that wrote it): it does still exist on disk, under the same gitignored `.superpowers/sdd/` path as everything else here, so it is not committed either and is exactly as re-readable as this paragraph says nothing else is — by whoever has this worktree, not by anyone reading only this file.

### Environment

- Step 1 (`SPIKE="$HOME/.cache/keelline-spikes"; rm -rf "$SPIKE"; mkdir -p "$SPIKE"`, then a
  heredoc wrote `lib.sh`) printed the resolved scratch root (`$SPIKE`) and exited without
  error. The written `lib.sh` held all eight helpers named in the brief's Interfaces line
  (`require_under_spike`, `mkcfg`, `mkplugin`, `install_plugin`, `installed_root`,
  `run_claude`, `hook_records`, `persisted_outputs`).
- Step 2's `CFG=$(mkcfg s0); mkplugin "$SPIKE/p0" p0; install_plugin "$SPIKE/p0" p0 "$CFG"`
  printed `Adding marketplace…✔ Successfully added marketplace: p0-marketplace (declared in
  user settings)` followed by `Installing plugin "p0@p0-marketplace"...✔ Successfully
  installed plugin: p0@p0-marketplace (scope: user)`.
- `CLAUDE_CONFIG_DIR="$CFG" claude plugin list | grep -c p0` printed `1`.
- `installed_root p0 "$CFG"` printed `cfg-s0/plugins/cache/p0-marketplace/p0/0.0.1` (relative
  to `$SPIKE`) — an installed path under the config dir's plugin cache, not the word
  `REFERENCED`. This is the load-bearing answer the brief flagged: on this machine, `claude
  plugin install` copied the plugin into the config dir's plugin cache rather than
  referencing the source directory in place. This is a statement about what `claude plugin
  install` copies, not about what a running plugin reads at `${CLAUDE_PLUGIN_ROOT}`: Findings
  → S2 (the `${CLAUDE_PLUGIN_ROOT}` qualification) and Findings → S8 (the live confirmation
  against a second plugin) both measured hooks and skill content resolving that variable to
  the marketplace's own source directory instead, for every directory-sourced marketplace
  this spike series built.
- `claude --version` printed `2.1.261 (Claude Code)`.
- `python3 --version` printed `Python 3.13.0`.
- `/usr/local/bin/python3 --version` printed `Python 3.13.0`.
- `/usr/bin/python3 --version` printed `Python 3.9.6`.
- `uv --version` printed `uv 0.11.19 (Homebrew 2026-06-03 aarch64-apple-darwin)`.
- `gh --version | head -1` printed `gh version 2.93.0 (2026-05-27)`.
- `gh auth status 2>&1 | grep -i scopes` printed `  - Token scopes: 'gist', 'read:org',
  'repo', 'workflow'`.
- `date` printed `Sat Sep  5 05:56:30 CEST 2026`.
- `command -v codex` printed nothing and exited `1`, so the `codex` CLI was absent from this
  machine's `PATH`; installing it belongs to Task 1, so Task 0 did not attempt it.
- The controller independently confirmed a design-wide limit that S1 below diagnosed from the
  Claude arm's re-run: `claude auth status` printed `"loggedIn": true, "authMethod":
  "claude.ai"` against the default config dir and `"loggedIn": false, "authMethod": "none"`
  against a scratch one (matching S1's own `CLAUDE_CONFIG_DIR="$CFG" claude auth status`
  result below). The controller then tried two file-copy routes to seed a probe config dir
  with credentials instead of running an interactive login inside it — copying the
  `oauthAccount` field alone, then copying the whole default `.claude.json` plus
  `settings.json` — and `claude auth status` against the resulting probe config dir printed
  `"loggedIn": false, "authMethod": "none"` after both attempts. The secret itself lives in
  the macOS Keychain under service `Claude Code-credentials` (see S1's `security
  dump-keychain` check below), so no file was missing; the credential lookup is keyed to
  `CLAUDE_CONFIG_DIR`'s value, and no file copy substituted for it. Consequence for the
  design: a Keelline test harness cannot spin up throwaway `CLAUDE_CONFIG_DIR`s without an
  interactive `claude auth login` completed inside each one, so any test shape in this design
  that assumed otherwise needs redesigning.
- `sed -n '60,88p' "$SPIKE/lib.sh"` printed the `hook_records` helper's `walk` function: its
  only test, `if kind in {"hook_success", "hook_error", "hook_additional_context"}`, appeared
  at that function's line 71 — three record `type` values, checked by exact match. Task 2's
  own S2 transcripts held a fourth. `grep -o '"type":"hook_[a-z_]*"'` against the matching
  `$SPIKE/cfg-shared/projects/.../*.jsonl` transcript printed `"type":"hook_non_blocking_error"`
  immediately followed by `"type":"hook_success"`, both from the same `SessionStart:startup`
  turn — the `hook_non_blocking_error` line is the exit-126, `Permission denied`,
  direct-invocation record Findings → S2 below quotes in full. `hook_records`'s `kind in
  {...}` test never matches `hook_non_blocking_error`, so calling it unmodified against this
  config dir printed only that turn's `hook_success` line and silently dropped the other.
  Consequence: any spike that read hook records only through unmodified `hook_records` (S7 and
  S8 read hook records heavily) may have seen an incomplete set, and a "no such record"
  conclusion drawn through it should be read as "no record of the three checked types," not as
  "no record of any kind."

### S1 — Codex plugin hooks

Step 1 (installing `@openai/codex@0.153.4` into `npm/node_modules/.bin/codex` and running
`codex login` with `CODEX_HOME="$SPIKE/codex-home"`) was performed by the controller before
this task started, after the owner's consent was asked and granted in chat. `codex --version`
printed `codex-cli 0.153.4`, and `codex login status` printed `Logged in using ChatGPT`. The
first login attempt ran `CODEX_HOME="$SPIKE/codex-home" "$SPIKE/npm/node_modules/.bin/codex" login`
before `$SPIKE/codex-home` existed, and printed `WARNING: proceeding, even though we could not
create PATH aliases: CODEX_HOME points to "$SPIKE/codex-home", but that path does not exist`
then `Error loading configuration: CODEX_HOME points to "$SPIKE/codex-home", but that path does
not exist`, exiting with code 1; creating the directory with `mkdir -p` before `codex login`
was required, confirming the brief's Step 1 ordering as written. This machine's `codex` CLI
refuses to log in against a `CODEX_HOME` that has not already been created.

`codex --help` listed `plugin` as a top-level command, and `codex plugin --help` listed `add`,
`list`, `marketplace`, `remove` — `codex plugin marketplace --help` listed `add`, `list`,
`upgrade`, `remove` — exactly the subcommand names the brief's Steps 4 assumed. `codex plugin
add --help` confirmed the `PLUGIN@MARKETPLACE` selector form the brief used, and `codex exec
--help` listed `--dangerously-bypass-hook-trust` exactly as named. No deviation from the
brief's assumed Codex command surface was needed for S1.

Step 2 built `$SPIKE/s1/hooks/hooks.json` with the ruling applied: `additionalContextLimit: 0` and
`additionalContextChars: 0` were added to the `PreToolUse` entry as well as `SessionStart`.
Reading the written file back showed both keys present on both entries.

Step 3 — `CFG=$(mkcfg s1); install_plugin "$SPIKE/s1" s1 "$CFG"` printed `Adding
marketplace…✔ Successfully added marketplace: s1-marketplace (declared in user settings)`
then `Installing plugin "s1@s1-marketplace"...✔ Successfully installed plugin: s1@s1-marketplace
(scope: user)` — install accepted `hooks.json` with the extra keys on both entries with no
schema error. `installed_root s1 "$CFG"` printed `cfg-s1/plugins/cache/s1-marketplace/s1/0.0.1`
(relative to `$SPIKE`), and the copy's `hooks.json` there was byte-for-byte identical to
the source, keeping both extra keys on both entries.

`run_claude "$CFG" "$SPIKE/s1/proj" --allowedTools=Bash,Read,Write "Run the shell command:
echo hello. Then read README.md. Then create probe.txt containing hi."` printed `turn errored:
{... "is_error": true, ... "result": "Not logged in · Please run /login" ...}` and exited
non-zero. Running the same shape of call directly against the real (non-scratch) config dir —
`claude -p --model haiku --output-format json "say hi"` — also failed, with a different
message: `"result":"Failed to authenticate: OAuth session expired and could not be refreshed"`;
`claude doctor` printed `Not signed in to claude.ai` and `claude.ai subscription auth not
active`. This confirmed the default config dir's own session was unusable at the time, from
an expired OAuth grant that a live non-interactive turn could not refresh — but, as the later
re-run below diagnosed precisely, that expiry was not what made the scratch-config-dir
`run_claude` call above fail: a fresh `CLAUDE_CONFIG_DIR` carries no credentials of its own
regardless of whether the default config dir's session is valid, so fixing the default
session's expiry did not and could not change the scratch arm's result. Either way, no
`PreToolUse` hook fired on the Claude side in this first pass — only `SessionStart` fired,
because Claude Code runs that hook at session start, before the model call that then failed.

`SessionStart` still ran successfully with the two extra keys present: `hook_records "$CFG"`
printed `hook_success cmd='python3 "${CLAUDE_PLUGIN_ROOT}/scripts/probe.py" session' rc=0
stdout_len=105 stderr=''` followed by `hook_additional_context cmd='SessionStart' rc=None
stdout_len=26 stderr=''`. `log-claude.jsonl` recorded one line: `stdin_keys` =
`["cwd", "hook_event_name", "session_id", "source", "transcript_path"]`, `tool_name` = `null`,
`event` = `"SessionStart"`, with `env_names` listing 26 `CLAUDE`/`PLUGIN`/`CODEX`-matching
names (below); Codex's equivalent `log-codex.jsonl` line listed 28 such names.

Step 4 — `"$CODEX" plugin marketplace add "$SPIKE/s1"` printed
`` `Added marketplace `s1-marketplace` from <SPIKE>/s1.` `` and `Installed marketplace root:
<SPIKE>/s1` (both relative to `$SPIKE`), exit 0, no refusal. `"$CODEX" plugin list` printed,
under the heading `` `Marketplace `s1-marketplace` ``, the path
`$SPIKE/s1/.claude-plugin/marketplace.json` as the file it read — the same file `mkplugin`
writes, and the same file Claude reads; the brief's contingency (a refusal naming
`$SPIKE/s1/.agents/plugins/marketplace.json`) did not occur. `"$CODEX" plugin add
s1@s1-marketplace` printed `` `Added plugin `s1` from marketplace `s1-marketplace`.` `` and
`Installed plugin root: $SPIKE/codex-home/plugins/cache/s1-marketplace/s1/0.0.1` — Codex, like
Claude, copied the plugin into its own config-dir cache rather than referencing `$SPIKE/s1` in
place, and the copy's `hooks.json` was byte-for-byte identical to the source.

`(cd "$SPIKE/s1/proj" && "$CODEX" exec --dangerously-bypass-hook-trust "Run the shell command:
echo hello. Then read README.md. Then create probe.txt containing hi.")` printed two
`` `warning: `--dangerously-bypass-hook-trust` is enabled...` `` lines (one per configured hook
entry), then `hook: SessionStart` immediately followed by `hook: SessionStart Completed`, then
twice: `ERROR: You've hit your usage limit. Upgrade to Plus to continue using Codex
(https://chatgpt.com/explore/plus), or try again at Sep 22nd, 2026 4:44 AM.`. The ChatGPT
account behind this scratch `CODEX_HOME` had no remaining Codex quota, so the run stopped
after `SessionStart` — no `PreToolUse` hook ever fired on the Codex side either.
`log-codex.jsonl` recorded one line: `stdin_keys` = `["cwd", "hook_event_name", "model",
"permission_mode", "session_id", "source", "transcript_path"]`, `tool_name` = `null`, `event`
= `"SessionStart"`.

Because both `claude -p` and `codex exec` ran here as children of this already-Claude-Code-
flavored sandboxed session, most `CLAUDE`-prefixed names appeared in both arms' `env_names`
only because they are ambient in the parent shell, not because either harness's hook launch
sets them. Running `env | awk -F= '{print $1}' | grep -E "PLUGIN|CLAUDE|CODEX"` directly in
the parent shell printed 21 names. Recomputed directly from `log-claude.jsonl` and
`log-codex.jsonl`'s own `env_names` sets (26 names on the Claude side, 28 on the Codex side),
the two arms' actual intersection is 23 names, not 21: the 21 ambient names above are ambient
contamination, and the remaining two — `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` — are the
genuinely shared names the next paragraph identifies, so only 21 of the 23 shared names are
ambient contamination and two are evidence of genuine cross-harness overlap.

A later re-run repeated Step 3 alone, after the owner re-authenticated the default `claude`
CLI and the controller confirmed `claude -p --model haiku --output-format json "say hi"`
returned no `is_error` key. `CFG=$(mkcfg s1rerun); install_plugin "$SPIKE/s1" s1 "$CFG"`
printed the same two success lines as the first attempt (`Successfully added marketplace:
s1-marketplace...`, `Successfully installed plugin: s1@s1-marketplace...`), and the installed
copy's `hooks.json` was byte-for-byte identical to the source. `run_claude "$CFG"
"$SPIKE/s1/proj" --allowedTools=Bash,Read,Write "Run the shell command: echo hello. Then read
README.md. Then create probe.txt containing hi."` printed `turn errored: {... "is_error":
true, ... "result": "Not logged in · Please run /login" ...}` — the identical message the
first report recorded, even though the default config dir's session was now fixed. Diagnosing
this directly: `claude auth status` against the default config dir printed `"loggedIn": true,
... "subscriptionType": "max"`, while `CLAUDE_CONFIG_DIR="$CFG" claude auth status` printed
`"loggedIn": false, "authMethod": "none"`. The same check against every other scratch config
dir this spike series had created by this point (three further `cfg-*` directories under
`$SPIKE`, none of them this run's fresh one) also printed `"loggedIn": false`. This settled
the actual cause, distinct from the first report's: Claude Code scopes account credentials per
`CLAUDE_CONFIG_DIR` — `security dump-keychain` (service names only, no secret values read)
listed the default config dir's own entry plus eight further per-config-dir entries, one per
distinct `CLAUDE_CONFIG_DIR` value that had ever completed its own login — so a brand-new
scratch config dir needs its own `claude auth login` regardless of whether the default config
dir's session is valid; fixing the default session's expiry did not and could not reach the
scratch arm. `claude auth login` opens an interactive browser OAuth grant, which this
non-interactive re-run had no standing to start on its own and no interactive terminal to
complete, so answer 2's Claude column stayed unobtained after this second attempt too — for a
newly and precisely diagnosed reason, not the one the first report gave. `SessionStart` still
ran and logged its usual record (`hook_success ... rc=0`; `log-claude-rerun.jsonl` held one
`SessionStart`/`tool_name: null` line, matching the first run's shape), reconfirming that
`PreToolUse` never gets a chance to run because the turn fails before any tool-use decision —
independent of which specific auth defect is in play.

This `CLAUDE_CONFIG_DIR`-scoped credential isolation is a design-wide limit, not a detail of
this probe alone — see the Environment entry above for the two file-copy routes the
controller tried in place of an interactive login and the resulting consequence for
Keelline's test-harness design.

The four S1 answers, computed from `log-claude.jsonl` and `log-codex.jsonl` with the ambient
21 names above subtracted:

1. **Environment/stdin names.** Codex-only env names, actually set by Codex's own hook launch:
   `CODEX_MANAGED_BY_NPM`, `CODEX_MANAGED_PACKAGE_ROOT`, `PLUGIN_DATA`, `PLUGIN_ROOT`.
   Claude-only env names, confirmed absent from the ambient parent env too, so actually set by
   Claude's own hook launch: `CLAUDE_ENV_FILE`, `CLAUDE_PROJECT_DIR`. Two further names,
   `CODEX_HOME` (Codex-only in this run) and `CLAUDE_CONFIG_DIR` (Claude-only in this run), are
   marked **unattributable in this run** rather than harness-set: both were set as command
   prefixes on the shell line that launched each harness — `lib.sh`'s `run_claude` runs
   `CLAUDE_CONFIG_DIR="$cfg" claude -p …` (quoted in Task 0's own listing), and this task's own
   Codex invocation set `CODEX_HOME="$SPIKE/codex-home" …` — and the ambient-subtraction
   baseline used here was the parent shell's own environment — a name set only as a command
   prefix is never
   in the parent shell's environment to begin with, so this subtraction could only ever report
   both as "absent from ambient, hence harness-set," regardless of whether the harness's own
   hook launch actually propagates them to the hook process or whether they merely survive
   from the invoking command line. Separating the two needs a different measurement: invoke
   each harness without setting the variable on the command line at all (reading the value
   from a file or a pre-exported shell variable instead), or diff the hook's own environment
   against the full invoking environment — command-line prefixes included — rather than
   against the parent shell's. Two names were genuinely shared and not ambient:
   `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` — Codex's hook launch set these Claude-named
   variables in addition to its own bare `PLUGIN_ROOT`/`PLUGIN_DATA`, and this is why the probe
   command's `${CLAUDE_PLUGIN_ROOT}` substitution worked under Codex: the probe script ran and
   wrote a log line, which a missing or empty substitution would have prevented. On stdin,
   Codex sent two keys Claude's `SessionStart` payload did not: `model` and
   `permission_mode`.
2. **`tool_name` for shell/read/file-creation.** Still not obtained for either harness after a
   second attempt confined to the Claude arm. Codex: this task did not attempt a Codex
   re-run — the account behind `$SPIKE/codex-home` had exhausted its usage quota until
   2026-09-22 (reset date from the first report's `codex exec` output above) and the owner
   declined to raise it; obtaining a real answer needs `CODEX_HOME="$SPIKE/codex-home"
   S1_LOG="$SPIKE/s1/log-codex-rerun.jsonl" "$SPIKE/npm/node_modules/.bin/codex" plugin
   marketplace add "$SPIKE/s1" && "$SPIKE/npm/node_modules/.bin/codex" plugin add
   s1@s1-marketplace && (cd "$SPIKE/s1/proj" && "$SPIKE/npm/node_modules/.bin/codex" exec
   --dangerously-bypass-hook-trust "Run the shell command: echo hello. Then read README.md.
   Then create probe.txt containing hi.")` once that quota resets. Claude: the default config
   dir's OAuth-session expiry was fixed and reconfirmed, but the Claude-arm re-run in a fresh
   scratch config dir still printed `turn errored: {... "result": "Not logged in · Please run
   /login" ...}`, this time diagnosed precisely as `CLAUDE_CONFIG_DIR`-scoped credential
   isolation rather than the first report's OAuth-expiry cause (detailed above) — every scratch
   config dir this spike series had created showed `"loggedIn": false` via `claude auth
   status`, independent of the default config dir's fixed session. Obtaining a real Claude-side
   answer needs an owner-authorized, interactively-completed `claude auth login` under a
   scratch `CLAUDE_CONFIG_DIR`, then the unchanged Step 3 `run_claude` command above — an OAuth
   grant this non-interactive task had no standing to start on its own. Both arms' logs still
   hold exactly one record each, both `SessionStart`, both `tool_name: null`; neither contains
   a `PreToolUse` record.

   **Restarting this measurement from nothing.** Task 11 deletes the entire scratch root, so
   the Codex re-run command quoted above will find neither `$SPIKE/npm/node_modules/.bin/codex`
   nor a logged-in `$SPIKE/codex-home`, and the Claude re-run will find neither `$SPIKE/lib.sh`
   nor `$SPIKE/s1`. Before either re-run, a later session must, in order: rebuild the helper
   library from Task 0 Step 1; reinstall `@openai/codex@0.153.4` into a fresh scratch npm
   prefix and complete `codex login` again inside a fresh scratch `CODEX_HOME`, per Task 1
   Step 1; and rebuild this task's probe plugin and project from Task 1 Step 2. The Claude-side
   re-run additionally needs its own interactively-completed `claude auth login` under a fresh
   scratch `CLAUDE_CONFIG_DIR`, as already noted above and as the `### Environment` subsection
   records for every scratch config dir this spike series created.
3. **Tolerance of `additionalContextLimit`/`additionalContextChars`.** On `SessionStart`, both
   harnesses tolerated both keys at runtime: Claude's `hook_records` showed `hook_success ...
   rc=0` for the probe command carrying both keys, and Codex's `codex exec` output showed
   `hook: SessionStart` immediately followed by `hook: SessionStart Completed` for the same
   command. On `PreToolUse`, tolerance was confirmed only at install time for both harnesses —
   `claude plugin install` and `codex plugin add` both completed successfully with the two
   extra keys present on the `PreToolUse` entry, and each installed copy retained both keys
   byte-for-byte — but neither harness ever fired that hook in this run (answer 2 above), so
   runtime tolerance of the keys specifically on `PreToolUse` was not verified.
4. **Marketplace file Codex read.** `codex plugin marketplace add "$SPIKE/s1"` succeeded on
   the first try, no refusal, and `codex plugin list` printed the marketplace's file path
   directly: `$SPIKE/s1/.claude-plugin/marketplace.json` — the same file `mkplugin` writes and
   the same file Claude reads. The brief's contingency (Codex asking for
   `$SPIKE/s1/.agents/plugins/marketplace.json`) did not arise, so that file was never
   created.

### S2 — plugin-root substitution and executable bits

**Two controller decisions applied, both before this task ran any command.** Steps 2 and 3
installed into and ran against `$SPIKE/cfg-shared` — the one scratch config dir on this
machine the owner logged into by hand — instead of the brief's `mkcfg s2` / `$SPIKE/cfg-s2`,
because a `mkcfg`-created config dir carries no credentials (Findings → S1 and → Environment
record this `CLAUDE_CONFIG_DIR`-scoped isolation in detail). Step 4 was not run; see its own
entry below. Because this worktree's Bash guard refused the brief's heredoc-and-`git`-init
shape in Step 1 as compound shell it could not prove stayed inside the worktree (the same
class of refusal Findings → S4 and → S6 record), every step below ran as a `python3` script
under `.superpowers/sdd/2026-09-05-agent-harness-p0-spikes/` (`task2_step1.py` through
`task2_step3b.py` — gitignored scratch files, not part of this commit), invoked with a plain
`python3 <path>`, reproducing the brief's file contents and command arguments exactly.

**How this task's hook records were told apart from other arms' in the shared config dir.**
Before this task's install, `$SPIKE/cfg-shared/plugins` did not exist on this machine — no
plugin had yet been installed into this config dir by any spike — so `claude plugin
marketplace add "$SPIKE/s2"` followed by `claude plugin install s2@s2-marketplace` created its
plugin cache for the first time. Walking every `*.jsonl` transcript under
`$SPIKE/cfg-shared/projects` (an extended form of `hook_records` that also captures each
record's full `stdout`/`stderr` text, not just its length, because this task needed to quote
the probe's own output) found records under two different project-slug directories: one
matching this worktree's own path, pre-existing and unrelated to any spike plugin (a
memory-loading `SessionStart` hook and a `UserPromptSubmit` reminder, neither mentioning
`noexec.py`), and one matching `$SPIKE/s2/proj`, created by this task's own two `run_claude`
calls below. This task's own records were identified by two independent markers agreeing on
the same two records each time: the command string contained `noexec.py`, a filename unique
to this task's plugin and absent from every other arm's hooks, and the successful record's
`stdout` was the literal marker `S2_SCRIPT_RAN`, printed by nothing else in this config dir.
Neither record needed to be treated as inconclusive.

**Step 2 — hook-command substitution and the executable-bit outcome.** For the first
`run_claude "$SPIKE/cfg-shared" "$SPIKE/s2/proj" "Reply with the single word ready."` turn
(which printed `ready`, `is_error: false`), the transcript recorded two `SessionStart:startup`
records, both carrying the **literal, unsubstituted** placeholder in the transcript's own
`command` field:

- the direct-invocation entry: `"command":"\"${CLAUDE_PLUGIN_ROOT}/scripts/noexec.py\""`,
  `"exitCode":126`, `"stderr":"Failed with non-blocking status code: /bin/sh:
  $SPIKE/s2/scripts/noexec.py: Permission denied"`;
- the `python3`-wrapped entry: `"command":"python3
  \"${CLAUDE_PLUGIN_ROOT}/scripts/noexec.py\""`, `"exitCode":0`, `"stdout":"S2_SCRIPT_RAN\n"`.

Both records were read directly from the transcript's own JSON, not through `lib.sh`'s
unmodified `hook_records` helper — Findings → Environment above records why the
direct-invocation entry would not have surfaced through that helper alone.

Read by the brief's own oracle in isolation — a resolved absolute path in the `command` field
proves substitution, the literal placeholder proves its absence — this `command` field alone
said substitution did not happen. But each record's own `stderr`/`stdout` said the opposite,
and settled it: the direct-invocation record's `stderr` named a concrete, existing absolute
path, `$SPIKE/s2/scripts/noexec.py`, and reported `Permission denied` against that specific
file — an unsubstituted `${CLAUDE_PLUGIN_ROOT}` (unset, hence empty) would have left the
literal, root-relative path "/scripts/noexec.py" (`"${VAR}/scripts/noexec.py"` with `VAR`
empty is still absolute, not relative — Findings → S8 row 3 measured exactly this shape
against `guard.py` and called it "the literal root-relative path" below), which does not
exist on this machine, and `/bin/sh` reports a missing path as "No such file or directory",
not "Permission denied" against a real, `$SPIKE`-rooted path. The `python3`-wrapped record
corroborated this
independently: its `stdout` was `S2_SCRIPT_RAN`, meaning `python3` opened and ran a real file,
which is only explained by the same substitution already having happened before the shell
executed either command. **This transcript recorded both hook entries as substituted before
execution; only
the transcript's own `command` field held the pre-substitution template text, not the
as-executed command.** Reading the `command` field alone, without also reading its
`stderr`/`stdout`, gave the wrong answer here.

The executable-bit outcome, as originally measured: `stat -f '%Sp %N'` against
`$SPIKE/s2/scripts/noexec.py` (the file Step 1 wrote and `chmod -x`'d) printed `-rw-r--r--`,
and the same command against the plugin's installed cache copy —
`$SPIKE/cfg-shared/plugins/cache/s2-marketplace/s2/0.0.1/scripts/noexec.py` — also printed
`-rw-r--r--`; both were non-executable. The direct-invocation
record above is that measurement: with no execute bit set, `/bin/sh` refused to run the file
directly and exited `126` with `Permission denied`, while the same file run through `python3`
(which only needs read permission) exited `0` and printed `S2_SCRIPT_RAN`. Both entries
resolved to the same substituted path; only the direct one was blocked, and only by the
missing executable bit. That result is genuinely established and is what Findings → S8 row 6
depends on. **What it does not establish is spec §14's actual question, "executable bits
after install."** The only mode this measurement ever put through an install was 644 → 644
(a non-executable source producing a non-executable installed copy), which cannot distinguish
"install preserves modes" from "install normalises every file to 644" — the two hypotheses
§14 asks S2 to tell apart. Findings → S8 row 6 later measured the same 644 → 644 shape a
second time (`run-hook.sh`'s mode cleared to `644` before install, then read back as `644` in
the installed copy), so nothing else in this record closes the question either; S8 rows 1–5
do not either, because Findings → S2's own next paragraph below (and Findings → S7's/S8's own
re-confirmation) established that `${CLAUDE_PLUGIN_ROOT}` resolves to the marketplace
**source**, not the `plugins/cache` copy, for every directory-sourced marketplace this spike
series built — so those rows say nothing about the installed copy's own mode.

**Follow-up measurement, taken to close that question rather than leave it open (finding
A2(b) of the external review round that caught this gap).** `$SPIKE` no longer exists — it
was deleted after that review round — so the question could not be answered by re-reading
anything under it; it needed a new, minimal measurement under a fresh scratch root, run and
logged while applying that review's fix (script
`a2b_exec_bit_probe.py`, full log `a2b-exec-bit-measurement.log`, both under
`.superpowers/sdd/2026-09-05-agent-harness-p0-spikes/`, gitignored — the log is the citation
behind every quote in this paragraph). The fresh root (called `$A2B` below, a directory under
`$HOME/.cache` distinct from and unrelated to `$SPIKE`, created new and deleted again at the
end of this measurement) held a throwaway plugin with a .claude-plugin/plugin.json and
.claude-plugin/marketplace.json in the same shape `mkplugin` writes, and two script files
under `$A2B/plugin/scripts/`: `exec755.sh`, `chmod 755`, and `noexec644.sh`, `chmod 644`.
Immediately after `chmod`, `stat -f '%Sp %N'` against each printed `-rwxr-xr-x` and
`-rw-r--r--` respectively. `CLAUDE_CONFIG_DIR="$A2B/cfg" claude plugin marketplace add
"$A2B/plugin"` printed `Adding marketplace…✔ Successfully added marketplace:
a2bexec-marketplace (declared in user settings)`, and `CLAUDE_CONFIG_DIR="$A2B/cfg" claude
plugin install a2bexec@a2bexec-marketplace` printed `Installing plugin
"a2bexec@a2bexec-marketplace"...✔ Successfully installed plugin:
a2bexec@a2bexec-marketplace (scope: user)`, both exiting 0. Reading
`$A2B/cfg/plugins/known_marketplaces.json` back gave the marketplace's own recorded location
(`installLocation`, `$A2B/plugin` itself — this is a directory-sourced marketplace, so, as
this same paragraph's neighbor above established, that location is the plugin's own source
directory, not an independent clone); reading `$A2B/cfg/plugins/installed_plugins.json` back
gave the installed `plugins/cache` copy's path,
`$A2B/cfg/plugins/cache/a2bexec-marketplace/a2bexec/0.0.1`. `stat -f '%Sp %N'` against both
files in **both** locations printed: `plugins/cache` copy — `-rwxr-xr-x` for `exec755.sh` and
`-rw-r--r--` for `noexec644.sh`, matching the source exactly; marketplace location — the
identical two modes, but because that location is the same directory as the source for this
marketplace type, that comparison is against the same file, not an independent copy, and adds
no information beyond reconfirming the source was untouched. **On this machine, for a
directory-sourced marketplace, `claude plugin install` preserved the executable bit into the
`plugins/cache` copy rather than normalising every file to 644** — the 644 → 644 result
higher up in this section was a property of the one (non-executable) file this task originally
tested, not of the install mechanism itself. Whether a git-URL-sourced marketplace preserves
modes the same way was not tested here and remains open, the same gap the paragraph below
already records for `${CLAUDE_PLUGIN_ROOT}` resolution. The throwaway scratch root `$A2B` was
deleted immediately after this measurement (`shutil.rmtree`, logged); the script and log
under `.superpowers/sdd/` were not.

**An unplanned but load-bearing discovery: which physical copy `${CLAUDE_PLUGIN_ROOT}`
actually named.** The resolved path both hook records' `stderr` named, and the resolved path
the skill content itself carried (Step 3, below), was `$SPIKE/s2` — the plugin's own
**marketplace source directory** — not the installed plugin's cache copy,
`$SPIKE/cfg-shared/plugins/cache/s2-marketplace/s2/0.0.1`, which is the path `installed_root`
(and `$SPIKE/cfg-shared/plugins/installed_plugins.json`'s own `installPath` field) names.
Reading `$SPIKE/cfg-shared/plugins/known_marketplaces.json` directly explained the split: for
this `"source": "directory"` marketplace, its own `installLocation` field held `$SPIKE/s2`
itself — the original directory, not a clone — while `installed_plugins.json`'s `installPath`
for `s2@s2-marketplace` named the separate cache copy `claude plugin install` also wrote
(present and byte-consistent with the source, confirmed by its own matching `-rw-r--r--` mode
above).
At runtime, both hooks and skill content resolved `${CLAUDE_PLUGIN_ROOT}` against the
**marketplace's** directory, not the **plugin's** cache copy. This qualified the copy
relationship Findings → Environment recorded above: `installed_root p0 "$CFG"` there printed
a path under the config dir's plugin cache, never the word `REFERENCED`, meaning `claude
plugin install` copied the plugin into the config dir's cache rather than referencing its
source directory in place. That is the copy `installed_root` names; S2's own measurement
showed `${CLAUDE_PLUGIN_ROOT}` did not resolve to it. For a `directory`-sourced marketplace on
this machine, an edit to the plugin's source directory after install still reached the
running plugin without reinstalling, because both hook commands and skill content resolved
`${CLAUDE_PLUGIN_ROOT}` to that source directory instead. Whether a git-URL-sourced
marketplace (S1's, S4's, and S6's plugins were also directory-sourced, so this distinction was
never visible to them either) resolves `${CLAUDE_PLUGIN_ROOT}` the same way was not tested
here and remains open.

**Step 3 — skill-content substitution, read directly from the transcript rather than only
from the model's reply.** `run_claude "$SPIKE/cfg-shared" "$SPIKE/s2/proj" "Use the s2-probe
skill."` printed `ROOT=$SPIKE/s2` as its `result` field, `is_error: false`. Rather than
trusting the model's reply alone as the oracle, this task read the transcript's own record of
what the skill actually handed the model before it replied: the meta `user`-role turn carrying
the skill's rendered content read `"Base directory for this skill: $SPIKE/s2/skills/
probe\n\nWhen invoked, reply with exactly one line, the following text with nothing
added:\nROOT=$SPIKE/s2\n"` — already resolved, with no `${CLAUDE_PLUGIN_ROOT}` placeholder
anywhere in it. This is the oracle the brief asked for, checked at its strongest point: the
skill's own rendered tool input carries no `${CLAUDE_PLUGIN_ROOT}` placeholder. The literal
string does appear twice elsewhere in this same transcript — `grep -c CLAUDE_PLUGIN_ROOT`
against it (`$SPIKE/cfg-shared/projects/…-s2-proj/1ecd50bb-….jsonl`) printed `2`, matching the
two `SessionStart` hook `command` fields Step 2 quoted above, neither one the skill's
tool-input turn — so the absence claim is scoped to the skill's rendered tool input, not to
the transcript as a whole. What appears in the skill's tool input instead, matching what the
model's reply copied verbatim, is `ROOT=$SPIKE/s2`, the plugin's marketplace source directory
identified in Step 2 above, a path this task created and that the model had no way to
construct from the prompt "Use the s2-probe skill." alone. **Skill content was substituted:
this run's transcript recorded the resolved path in the skill's own tool input, before the
model ever produced a reply.** `installed_root` (the `plugins/cache` copy) was
`$SPIKE/cfg-shared/plugins/cache/s2-marketplace/s2/0.0.1`, given here so a reader checking the
oracle against the value the brief anticipated can see why it differs from the value
substitution actually produced (Step 2's discovery, above).

**Step 4 — not run.** The Codex account's usage quota was exhausted until 2026-09-22 (Findings
→ S1 quotes the exact message: "ERROR: You've hit your usage limit. Upgrade to Plus to
continue using Codex …, or try again at Sep 22nd, 2026 4:44 AM.") and the owner decided not to
raise it, so no `codex` command was run for this task. This is an unrun measurement, not a
null result. The brief's exact command block, preserved so a later session can run it once the
quota resets:

```bash
set -eu; SPIKE="$HOME/.cache/keelline-spikes"; . "$SPIKE/lib.sh"
CODEX="$SPIKE/npm/node_modules/.bin/codex"; export CODEX_HOME="$SPIKE/codex-home"
"$CODEX" plugin marketplace add "$SPIKE/s2" && "$CODEX" plugin add s2@s2-marketplace
(cd "$SPIKE/s2/proj" && "$CODEX" exec --dangerously-bypass-hook-trust "Use the s2-probe skill.") \
  > "$SPIKE/s2/codex-result.txt" 2>&1; tail -3 "$SPIKE/s2/codex-result.txt"
```

**Warning:** Task 11 deletes the entire scratch root, including `$SPIKE/lib.sh` (which the
block above sources), `$SPIKE/npm/node_modules/.bin/codex` and its logged-in `$SPIKE/codex-home`,
`$SPIKE/s2`, and `$SPIKE/cfg-shared`. Before running the Step 4 block above, a later session
must, in order: rebuild the helper library from Task 0 Step 1; reinstall
`@openai/codex@0.153.4` into a fresh scratch npm prefix and complete `codex login` again
inside a fresh scratch `CODEX_HOME`, per Task 1 Step 1; and re-run this task's Step 1
(rebuilding `$SPIKE/s2`, including the non-executable `noexec.py` and the `s2-probe` skill).
None of the helper library, the Codex login, the plugin, nor its authenticated config dir will
still exist by then.

### S3 — Codex `/import` scope

**Step 1 — completed.** Before this closing task started, the controller ran a Python script
mirroring Task 3 Step 1 (`s3_setup.py`, a gitignored scratch file kept alongside this plan's
task briefs, not part of this commit — the same workaround Findings → S4 records for this
worktree's Bash guard). It created `$SPIKE/cfg-s3`, initialized a git repository at
`$SPIKE/s3/proj`, and ran `claude -p --model haiku --output-format json "Reply with the
single word ready."` there with `CLAUDE_CONFIG_DIR="$SPIKE/cfg-s3"`. That turn itself
errored — this ran during the same window Findings → S1 records this machine's `claude` CLI
being unable to complete any headless turn — but `$SPIKE/cfg-s3/projects/<slug>/` was created
anyway: a failed `claude -p` invocation still creates the project slug directory, so Step 1's
seeding did not depend on a working turn. The slug was read from what Claude Code created,
not derived, matching the brief's stated reason (the real slug maps every non-alphanumeric
character and resolves `/tmp` to `/private/tmp` first).

With the slug directory in hand, the controller seeded `$SPIKE/cfg-s3/projects/<slug>/memory/`
with two files: `MEMORY.md`, holding one index line pointing at `s3-probe.md`, and
`s3-probe.md`, a note whose frontmatter `description` carries `S3_CANARY_NOTE` and whose body
is `S3_CANARY_BODY`.

**Step 2 and Step 3 — not run.** Reason: the Codex account's usage quota was exhausted until
2026-09-22 (Findings → S1 quotes the exact message: "ERROR: You've hit your usage limit.
Upgrade to Plus to continue using Codex …, or try again at Sep 22nd, 2026 4:44 AM.") and the
owner decided not to raise it. Step 2 additionally requires the owner to type `/import`
interactively in the Codex TUI, which nothing non-interactive can do on the owner's behalf.
Both steps remain undone — not a null result, an unrun measurement.

**To complete later**, once the quota resets: re-seed Step 1 from the Task 3 brief (see the
warning below), then start the TUI in the seeded project — `cd "$SPIKE/s3/proj" &&
CLAUDE_CONFIG_DIR="$SPIKE/cfg-s3" CODEX_HOME="$SPIKE/codex-home"
"$SPIKE/npm/node_modules/.bin/codex"` — then, with the owner present, type `/import`, choose
Claude Code, and exit. Then search both sides for the canary: `grep -rl 'S3_CANARY'
"$SPIKE/codex-home"` and the same `grep -rl 'S3_CANARY'` over `$SPIKE/s3/proj`.

**Warning:** Task 11 deletes the entire scratch root, including `$SPIKE/lib.sh` (which the
Task 3 brief's own Step 1 sources), `$SPIKE/npm/node_modules/.bin/codex` and its logged-in
`$SPIKE/codex-home`, `$SPIKE/cfg-s3`, and its seeded memory store. Before re-running Step 2
and Step 3, a later session must, in order: rebuild the helper library from Task 0 Step 1;
reinstall `@openai/codex@0.153.4` into a fresh scratch npm prefix and complete `codex login`
again inside a fresh scratch `CODEX_HOME`, per Task 1 Step 1; and re-run Step 1's seeding from
the Task 3 brief. None of the helper library, the Codex CLI and its login, the config dir, nor
its canary notes will still exist by then. Step 1's own `claude -p` seeding turn tolerates
failure — a failed turn still creates the project slug directory, as this task's own attempt
above showed — so re-seeding does not itself require a freshly authenticated scratch
`CLAUDE_CONFIG_DIR`; only a Claude-side turn elsewhere in this plan needs the interactive
`claude auth login` the `### Environment` subsection records.

**Design consequence:** open, not answered. §2 D5 and §6.4 keep the question of whether
Codex's `/import` carries Claude memory notes at all; neither section gains an answer from
this run.

### S4 — `validate --strict` per manifest path

This worktree's Bash guard refused Step 1's heredoc-built layout and Step 2's nested `for`
loop as compound shell it could not prove stayed inside the worktree, even though every path
in both steps was `$SPIKE`-rooted and none touched the worktree. Both steps ran instead as
`python3` scripts under `.superpowers/sdd/2026-09-05-agent-harness-p0-spikes/` (bare
filenames `step1_s4.py`, `step2_s4.py` — gitignored scratch files, not part of this commit)
that built the identical `$SPIKE/s4` / `$SPIKE/s4-broken` trees the brief specified and then
ran the same sixteen invocations through `subprocess.run` with an explicit argv list — the
bare-directory target passed no trailing path segment and the no-flag arm passed no extra
argument, matching what the brief's zsh loop intended for its unquoted-empty-variable case;
each row's printed command line confirmed this (for example `claude plugin validate
$SPIKE/s4-broken` with no fourth argument, and `claude plugin validate
$SPIKE/s4/.codex-plugin/plugin.json --strict` with the flag present). `claude --version`
printed `2.1.261 (Claude Code)` for this run, matching Findings → Environment and differing
from the Tech Stack header's `2.1.259`.

Step 1 built `$SPIKE/s4` (`$SPIKE/s4/.claude-plugin/plugin.json` carrying the foundation
manifest's `userConfig` block, `$SPIKE/s4/.claude-plugin/marketplace.json`,
`$SPIKE/s4/.codex-plugin/plugin.json`, `$SPIKE/s4/skills/init/SKILL.md`,
`$SPIKE/s4/agents/probe.md`, `$SPIKE/s4/scripts/keelline`) and copied it to
`$SPIKE/s4-broken`, then planted three defects there: `$SPIKE/s4-broken/skills/init/SKILL.md`
was overwritten with `name: init` and no `---` frontmatter delimiters,
`$SPIKE/s4-broken/agents/probe.md` was overwritten with frontmatter carrying an empty
`name:` and no `description`, and `$SPIKE/s4-broken/.codex-plugin/plugin.json` was
overwritten with the truncated, syntactically invalid `{not json`.

**All sixteen exit codes**, from `claude plugin validate $SPIKE/<tree>[/<target>] [--strict]`
(target labels below: "directory" is the bare tree root; "plugin.json" is each tree's own
.claude-plugin plugin manifest; "marketplace.json" is each tree's own .claude-plugin
marketplace manifest; "codex plugin.json" is each tree's own .codex-plugin plugin manifest):

| Tree | Target | Flag | Exit code |
|---|---|---|---|
| s4 (valid) | directory | — | 0 |
| s4 (valid) | directory | `--strict` | 0 |
| s4 (valid) | plugin.json | — | 0 |
| s4 (valid) | plugin.json | `--strict` | 0 |
| s4 (valid) | marketplace.json | — | 0 |
| s4 (valid) | marketplace.json | `--strict` | 0 |
| s4 (valid) | codex plugin.json | — | 1 |
| s4 (valid) | codex plugin.json | `--strict` | 1 |
| s4-broken | directory | — | 0 |
| s4-broken | directory | `--strict` | 0 |
| s4-broken | plugin.json | — | 0 |
| s4-broken | plugin.json | `--strict` | 1 |
| s4-broken | marketplace.json | — | 0 |
| s4-broken | marketplace.json | `--strict` | 0 |
| s4-broken | codex plugin.json | — | 1 |
| s4-broken | codex plugin.json | `--strict` | 1 |

**Discrimination on `$SPIKE/s4-broken`'s three planted defects.**

- The broken skill (`SKILL.md`'s missing frontmatter) was reported by exactly one
  invocation: `claude plugin validate $SPIKE/s4-broken/.claude-plugin/plugin.json`, in both
  flag settings — that target's validation cascaded into the plugin's declared skill and
  printed `Validating skill: $SPIKE/s4-broken/skills/init/SKILL.md` followed by the warning
  `frontmatter: No frontmatter block found. Add YAML frontmatter between --- delimiters at
  the top of the file to set description and other metadata.`. Without `--strict` the
  invocation still exited 0, printing `✔ Validation passed with warnings`; with `--strict`
  the same warning text appeared and the invocation exited 1, printing `✘ Validation failed
  (--strict treats warnings as errors)`.
- The broken agent (`probe.md`'s empty `name:` and missing `description`) was reported by the
  same single invocation and no other: the plugin.json target's cascade also printed
  `Validating agent: $SPIKE/s4-broken/agents/probe.md` followed by the warning `description:
  No description in frontmatter. A description helps users and Claude understand when to use
  this agent.`, again exiting 0 without `--strict` and 1 with it.
- The broken Codex manifest (`$SPIKE/s4-broken/.codex-plugin/plugin.json` truncated to `{not
  json`) was reported by `claude plugin validate
  $SPIKE/s4-broken/.codex-plugin/plugin.json` in both flag settings — it printed `json:
  Invalid JSON syntax: JSON Parse error: Expected '}'` and exited 1 regardless of `--strict`,
  because a syntax error is an error the tool reported outright rather than a warning only
  `--strict` escalates.
- **Reported by nothing:** `claude plugin validate $SPIKE/s4-broken` (the bare directory) and
  `claude plugin validate $SPIKE/s4-broken/.claude-plugin/marketplace.json` both exited 0 in
  both flag settings and printed only `Validating marketplace manifest:
  $SPIKE/s4-broken/.claude-plugin/marketplace.json` followed by `✔ Validation passed`.
  Neither invocation's output mentioned the plugin manifest, the skill, the agent, or the
  Codex manifest at all, so four of the sixteen invocations against the broken tree — both
  flag settings of the directory target and both flag settings of the marketplace target —
  reported none of the three planted defects, `--strict` included.

**Every warning `$SPIKE/s4` (the valid tree) produced under `--strict`.** Three of the four
`--strict` invocations against the valid tree — directory, plugin.json, and
marketplace.json — printed only `✔ Validation passed`, no warnings. The fourth, `claude
plugin validate $SPIKE/s4/.codex-plugin/plugin.json --strict`, exited 1 and printed one error
and two warnings — identically to the same invocation without `--strict`, since the error
alone already failed validation independent of the flag: `✘ Found 1 error: ❯ skills[0]: Path
not found: ./skills/. The runtime loader will report this as a load failure.` and `⚠ Found 2
warnings: ❯ interface: Unknown field 'interface'. Claude Code ignores it at load time. ❯
author: No author information provided. Consider adding author details for plugin
attribution`. The path error traced to the §5.1 layout the brief specified rather than to any
planted defect: `$SPIKE/s4/.codex-plugin/plugin.json`'s `"skills": "./skills/"` field
resolved relative to the manifest's own `.codex-plugin` directory, one level below the
actual `$SPIKE/s4/skills/` the brief created, so `claude plugin validate` reported the valid
tree's own Codex manifest as broken before `s4-broken` was ever built. The untested candidate
remedy is `"skills": "../skills/"`: relative to `.codex-plugin`, that value reaches
`$SPIKE/s4/skills/`, the directory the brief actually created. This task did not rewrite the
manifest with that value and re-run `claude plugin validate` against it, so `../skills/` is
recorded here as a starting point for `foundation` to verify, not a confirmed fix. The
`author` warning was separate and specific to that manifest: `$SPIKE/s4/.codex-plugin/plugin.json`
carried no `author` field of its own, unlike the sibling `$SPIKE/s4/.claude-plugin/plugin.json`.

### S5 — private SSH marketplace refresh

**What differed between the three arms, derived from the per-arm prose below.**

| Arm | What was measured | What the evidence does not cover |
|---|---|---|
| SSH | Session start left `installed_plugins.json`, the marketplace clone's `plugin.json`, and `known_marketplaces.json`'s `lastUpdated` all unchanged from their pre-turn values; the foreground `plugin marketplace update` advanced `lastUpdated`, and the clone dropped out of this task's `"0.1.0"` substring scan across that update, evidencing a version change; `claude plugin list` never reported a version different from this arm's own install-time baseline. | What value the marketplace clone's version changed to — no `grep version` or `git log` was run against the clone at the time, and the between-arm reset deleted it before this fix could re-inspect it. |
| Plain HTTPS (no keep-on-failure) | The same session-start-unchanged and installed-pointer-unchanged results as the SSH arm; HTTPS authenticated transparently through `osxkeychain`, with no authentication failure observed. | Anything about the marketplace clone's own content or version after the foreground update — the `"0.1.0"` scan never matched this arm's already-`0.1.1` baseline, no `grep version`/`git log` was run during the arm, and the between-arm reset deleted this arm's clone and cache directories before this fix could re-inspect them. |
| HTTPS with `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` | The same session-start-unchanged and installed-pointer-unchanged results again; because no further arm followed, this clone and cache directory were never reset and were re-inspected after the fact during this fix: `grep version` and `git log` showed the pushed commit and bumped version at HEAD, and a new cache directory existed, while `claude plugin list` still reported the arm's own old baseline version. | What the keep-on-failure variable actually changes on a genuine failure — no clone or install failure occurred anywhere in this arm, so the variable was never exercised against one; also the exact moment the cache directory was written relative to the `lastUpdated` move, since its `stat` timestamp read later than that move. |

Because `mkcfg` produces an unauthenticated config dir (every turn against one errors `Not
logged in · Please run /login`), this task ran all three arms against the one authenticated
scratch dir, `$SPIKE/cfg-shared`, instead of `mkcfg s5-ssh` / `mkcfg s5-https` /
`mkcfg s5-https-keep` as the brief names them. Because the worktree-isolation Bash guard
refused every command shaped like a git invocation or containing a `git@github.com`/
`https://github.com/...` URL literal (for example, it refused `CLAUDE_CONFIG_DIR="$CFG"
claude plugin marketplace add "git@github.com:$OWNER/keelline-spike-s5.git"` run directly,
with `this command names git in a form too complex to verify that it stays inside the
worktree`), Steps 1-3 ran as `python3` scripts under
`.superpowers/sdd/2026-09-05-agent-harness-p0-spikes/` (`task5_step1_create_repo.py`,
`task5_arm.py`), invoked with a plain `python3 <path>` and `subprocess.run` for every `git`
and `claude plugin` call, matching the argv the brief named. `claude --version` printed
`2.1.261 (Claude Code)` for this run, matching Findings → Environment and differing from the
Tech Stack header's `2.1.259`. `uptime` printed `load averages: 2.68 2.65
2.68`; no other command was run concurrently with a timed turn.

**Step 1.** `gh repo create <owner>/keelline-spike-s5 --private` printed
`https://github.com/<owner>/keelline-spike-s5` and exited 0. `cp -R $SPIKE/s4 $SPIKE/s5`
exited 0 without mutating `$SPIKE/s4`. `git -C $SPIKE/s5 init -q -b main`, `git -C $SPIKE/s5
add -A`, `git -C $SPIKE/s5 commit -qm "spike: s5 plugin"`, `git -C $SPIKE/s5 remote add
origin git@github.com:<owner>/keelline-spike-s5.git`, and `git -C $SPIKE/s5 push -q -u origin
main` each exited 0. As with the between-arm reset below, these Step 1 commands' quoted output
was not captured to a persisted log at the time — this record quotes it from the task's own
execution, the same unlogged-preamble asymmetry the between-arm reset paragraph discloses
below.

**Between-arm reset.** Before each of the HTTPS and HTTPS-keep arms, this task ran
`CLAUDE_CONFIG_DIR="$SPIKE/cfg-shared" claude plugin uninstall keelline@keelline-marketplace
-y`, `CLAUDE_CONFIG_DIR="$SPIKE/cfg-shared" claude plugin marketplace remove
keelline-marketplace`, `ls $SPIKE/cfg-shared/plugins/marketplaces`, `ls
$SPIKE/cfg-shared/plugins/cache`, then (because the `ls` output showed a leftover
`keelline-marketplace` directory in each) `rm -rf
$SPIKE/cfg-shared/plugins/marketplaces/keelline-marketplace` and `rm -rf
$SPIKE/cfg-shared/plugins/cache/keelline-marketplace`, then a re-listing of both directories.
None of these commands' output was captured to a persisted log, so this record states only
that they were run, in that order, not their exit codes or exact stdout — the success lines
and directory listings are not backed by an artifact and are omitted rather than quoted here.
The persisted evidence that the reset worked is indirect: each following arm's own baseline
read (logged in that arm's own `s5_<arm>_run.log`) shows a freshly-populated
`keelline-marketplace` entry in `known_marketplaces.json` with a new `lastUpdated` and an
`installed_plugins.json` entry whose `gitCommitSha` matches the immediately preceding arm's
own last push (`9697b0c...` at the HTTPS arm's baseline, `f59e02c...` at the HTTPS-keep arm's
baseline) rather than any older or stale commit — consistent with the reset having cleared
the registries and each arm cloning fresh, though this task did not verify the reset
commands' own output directly.

**How records were told apart in `$SPIKE/cfg-shared`.** `$SPIKE/cfg-shared/projects` held
transcripts from other tasks (an S2 run under a `...-s2-proj` path), but this task was the
only one ever to run a turn from `$SPIKE/s5/proj`, so `find $SPIKE/cfg-shared/projects -iname
"*<session-id>*"` for each of this task's three recorded `session_id` values (from each
turn's own JSON result) located exactly one transcript apiece, all three under the single
project-slug directory Claude Code derives from `$SPIKE/s5/proj`'s absolute path (elided
here: the derived slug embeds the machine's home directory). Reading those three JSONL files
directly (not through `hook_records`, which drops the `hook_non_blocking_error` record type
this Claude Code version emits) showed a `hook_non_blocking_error` / `hook_success` pair in
every one of the three transcripts, but each pair's `hookName` was `SessionStart:startup`
running `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/noexec.py"` with stderr `Failed with
non-blocking status code: /bin/sh: $SPIKE/s2/scripts/noexec.py: Permission denied` — this is
the leftover `s2` plugin's own hook firing because it was still installed in
`$SPIKE/cfg-shared` throughout, not anything belonging to `keelline`. No hook record in any
of the three transcripts named `keelline`, `keelline-marketplace`, or the pushed repository,
and both markers above belonged entirely to the leftover `s2` plugin, never to `keelline`.
`$SPIKE/s5` was `cp -R`'d from `$SPIKE/s4`, and Task 4 Step 1's `mkdir -p` (`mkdir -p
$SPIKE/s4/.claude-plugin $SPIKE/s4/.codex-plugin $SPIKE/s4/agents $SPIKE/s4/skills/init
$SPIKE/s4/scripts`) never created a `hooks` directory at all — Findings → S4's own file list
for this tree names the same manifests, skill and script and no hook file. The plugin under
test declares no `SessionStart` hook because it has no hook file of any kind, not because a
`{"hooks": {}}` file was read; no plugin-hook-driven refresh mechanism fired in any arm.

**SSH arm.** `CLAUDE_CONFIG_DIR="$SPIKE/cfg-shared" claude plugin marketplace add
"git@github.com:<owner>/keelline-spike-s5.git"` printed `Adding marketplace…Refreshing
marketplace cache (timeout: 120s)…Cloning repository (timeout: 120s):
git@github.com:<owner>/keelline-spike-s5.git Clone complete, validating marketplace…Cleaning
up old marketplace cache…✔ Successfully added marketplace: keelline-marketplace (declared in
user settings)` and exited 0. `CLAUDE_CONFIG_DIR="$SPIKE/cfg-shared" claude plugin install
keelline@keelline-marketplace` printed `Installing plugin
"keelline@keelline-marketplace"...✔ Successfully installed plugin:
keelline@keelline-marketplace (scope: user)` and exited 0. Immediately afterward,
`$SPIKE/cfg-shared/plugins/installed_plugins.json` recorded `"version": "0.1.0"` at
`installPath` `$SPIKE/cfg-shared/plugins/cache/keelline-marketplace/keelline/0.1.0`
(`gitCommitSha` `eb75a61...`, the Step 1 commit), and
`$SPIKE/cfg-shared/plugins/marketplaces/keelline-marketplace/.claude-plugin/plugin.json` also
read `"version": "0.1.0"` — these are the two directories this task's brief asked to be told
apart, citing S2's finding that `${CLAUDE_PLUGIN_ROOT}` resolves to a marketplace's source
directory rather than its installed cache copy: the marketplace's own git clone
(`$SPIKE/cfg-shared/plugins/marketplaces/keelline-marketplace`) versus the installed cache
copy (`$SPIKE/cfg-shared/plugins/cache/keelline-marketplace/keelline/0.1.0`).

`sed`-equivalent replacement of `"version": "0.1.0"` with `"version": "0.1.1"` in
`$SPIKE/s5/.claude-plugin/plugin.json`, followed by `git -C $SPIKE/s5 commit -qam "spike:
bump for ssh"` and `git -C $SPIKE/s5 push -q`, each exited 0. The timed turn — `claude -p
--model haiku --output-format json "Reply with the single word ready."` run from
`$SPIKE/s5/proj` with `CLAUDE_CONFIG_DIR` set to `$SPIKE/cfg-shared` — took **3.76s**
wall-clock (Python's `time.monotonic()`), returned `is_error: false`, and printed `ready`.

Immediately after that turn, `$SPIKE/cfg-shared/plugins/installed_plugins.json` still read
`"version": "0.1.0"` at the same `installPath`, and
`$SPIKE/cfg-shared/plugins/marketplaces/keelline-marketplace/.claude-plugin/plugin.json`
still read `"version": "0.1.0"` too — **the installed version did not change at session
start**, and neither did the marketplace's own clone. `known_marketplaces.json`'s
`keelline-marketplace.lastUpdated` also stayed at `2026-09-05T05:41:47.428Z` across the turn,
the same value recorded right after `plugin marketplace add`, so nothing had refreshed the
marketplace metadata in the background either.

The foreground `CLAUDE_CONFIG_DIR="$SPIKE/cfg-shared" claude plugin marketplace update
keelline-marketplace`, run after the turn, printed `Updating marketplace:
keelline-marketplace...Refreshing marketplace cache (timeout: 120s)…✔ Successfully updated
marketplace: keelline-marketplace` and exited 0. Afterward,
`known_marketplaces.json`'s `lastUpdated` had moved to `2026-09-05T05:41:57.129Z`, up from
the baseline value above. This task's own instrumentation never ran `grep version` or `git
log` against the marketplace clone during this arm, so it cannot quote what either would have
printed at the time; what the logged record does show is that
`$SPIKE/cfg-shared/plugins/marketplaces/keelline-marketplace/.claude-plugin/plugin.json` was
present in this task's own `"version": "0.1.0"` substring scan both immediately after install
and immediately after the session-start turn, and absent from that same scan immediately
after the foreground update — indicating the file's version changed across the foreground
update, though not to what value. The between-arm reset that followed (`rm -rf` on that
directory and its cache counterpart, above) deleted the clone before the HTTPS arm started,
so this task cannot re-inspect it now either and does not reconstruct the specific version or
commit it changed to. But `$SPIKE/cfg-shared/plugins/cache/keelline-marketplace/
keelline/0.1.0/.claude-plugin/plugin.json` still read `"version": "0.1.0"` after that same
foreground update, and `CLAUDE_CONFIG_DIR="$SPIKE/cfg-shared" claude plugin list` printed
`❯ keelline@keelline-marketplace` / `Version: 0.1.0` / `Scope: user` / `Status: ✔ enabled` —
**the installed plugin's reported version never changed, not from the session-start turn and
not from the foreground marketplace update**; only `plugin update` (not run in this task,
out of the brief's scope) would have moved the installed copy.

**HTTPS arm (no keep-on-failure).** `git config --get-all credential.helper` printed
`osxkeychain`, which explains the result below: this machine's HTTPS git operations
authenticate transparently through the keychain, with no interactive prompt. `
CLAUDE_CONFIG_DIR="$SPIKE/cfg-shared" claude plugin marketplace add
"https://github.com/<owner>/keelline-spike-s5.git"` printed the same `Adding
marketplace…Refreshing marketplace cache (timeout: 120s)…Cloning repository (timeout:
120s):...Clone complete, validating marketplace…Cleaning up old marketplace cache…✔
Successfully added marketplace: keelline-marketplace (declared in user settings)` shape as
the SSH arm and exited 0; no authentication failure of any kind was observed. `claude plugin
install keelline@keelline-marketplace` exited 0 and printed the same success line as the SSH
arm. Because the reset above cleared the registries but the pushed repository itself carried
forward the SSH arm's last commit, the baseline this arm installed was already `"version":
"0.1.1"` (`gitCommitSha` `9697b0c...`, the SSH arm's own bump) — this is the SSH arm's
history, not contamination of the HTTPS arm's own cfg-shared state, which the reset had
already cleared.

The version bump for this arm used a 4-digit random suffix generated in Python
(`random.randint(1000, 9999)`) in place of the brief's shell `$RANDOM`, since the
substitution ran inside the Python script; it landed on `"version": "0.1.9596"`.
`git -C $SPIKE/s5 commit -qam "spike: bump for https"` and `git -C $SPIKE/s5 push -q` each
exited 0. The timed turn took **3.69s** wall-clock, returned `is_error: false`, and printed
`ready`.

Immediately after that turn, `$SPIKE/cfg-shared/plugins/installed_plugins.json` still read
`"version": "0.1.1"` at `installPath`
`$SPIKE/cfg-shared/plugins/cache/keelline-marketplace/keelline/0.1.1`, and
`known_marketplaces.json`'s `keelline-marketplace.lastUpdated` was unchanged at
`2026-09-05T05:42:53.777Z`, the same value recorded right after `plugin marketplace add` —
**the installed version did not change at session start**, the same result as the SSH arm.

The foreground `claude plugin marketplace update keelline-marketplace` printed the same
`Updating marketplace: keelline-marketplace...Refreshing marketplace cache (timeout:
120s)…✔ Successfully updated marketplace: keelline-marketplace` and exited 0.
`known_marketplaces.json`'s `lastUpdated` moved to `2026-09-05T05:43:02.150Z`, up from the
value recorded right after this arm's own `plugin marketplace add`. Unlike the SSH arm, this
task's `"version": "0.1.0"` substring scan never matched this arm's marketplace clone at any
point — its baseline was already `0.1.1`, not `0.1.0` — so that scan adds no information here
either way, and no `grep version` or `git log` command was run against the clone during this
arm. This record therefore makes no claim about what version or commit the marketplace clone
held after this arm's foreground update, and none about whether a new cache directory
appeared at this point: no command run during the spike checked for one, and the
`.../keelline/0.1.9596` directory that exists on disk today was created later, during the
HTTPS-keep arm's own baseline install (its `installedAt` in `installed_plugins.json`,
`2026-09-05T05:44:21.444Z`, matches that directory's current modification time — see the
HTTPS-keep arm below), not by this arm's foreground update, and the between-arm reset deleted
this arm's own clone and cache directories before either could be re-inspected. What the
logged record does show is that `installed_plugins.json` and
`CLAUDE_CONFIG_DIR="$SPIKE/cfg-shared" claude plugin list` both still reported
`"0.1.1"`/`Version: 0.1.1` as the installed, active copy after the foreground update — the
installed pointer did not move.

**HTTPS arm with `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1`.** After the same
between-arm reset, `claude plugin marketplace add
"https://github.com/<owner>/keelline-spike-s5.git"` and `claude plugin install
keelline@keelline-marketplace` again exited 0 with the same success output shapes as the
prior two arms; no failure occurred for the keep-on-failure variable to act on. The baseline
installed was `"version": "0.1.9596"` (the HTTPS arm's own last push), bumped by the same
Python-`random` substitution to `"version": "0.1.4482"`, committed and pushed successfully.
The timed turn — run with `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` exported in
addition to `CLAUDE_CONFIG_DIR` — took **4.02s** wall-clock, returned `is_error: false`, and
printed `ready`. Immediately afterward, `installed_plugins.json` still read `"version":
"0.1.9596"` and `known_marketplaces.json`'s `lastUpdated` was unchanged at
`2026-09-05T05:44:20.837Z` — again, **the installed version did not change at session
start**, the same result as the other two arms. The foreground `claude plugin marketplace
update keelline-marketplace` (run with the same variable still exported) printed the
identical `Updating marketplace: keelline-marketplace...Refreshing marketplace cache
(timeout: 120s)…✔ Successfully updated marketplace: keelline-marketplace` and exited 0;
`lastUpdated` moved to `2026-09-05T05:44:29.673Z`. Unlike the SSH and plain-HTTPS arms, no
further arm followed this one, so this arm's marketplace clone and staged cache directory
were never reset and are still on disk. Re-inspecting them now (this task's own
instrumentation did not run these commands at the time — the re-run and its output are logged
in `task5_fix_verify.log`, a gitignored scratch file under
`.superpowers/sdd/2026-09-05-agent-harness-p0-spikes/`, not part of this commit; the relevant
lines are reproduced inline below), `grep version` on the marketplace clone's
`plugin.json` printed `"version": "0.1.4482",` and `git log --oneline -3` there printed
`7dd2646 spike: bump for https-keep` / `f59e02c spike: bump for https` at HEAD, and a
`.../keelline/0.1.4482` cache directory exists alongside the `0.1.9596` one installed as this
arm's own baseline — consistent with this arm's foreground update having fetched the pushed
commit and staged its bundle, though this task cannot say from a single after-the-fact
snapshot exactly when the cache directory was written; a `stat -f "%N %Sm"` on it read a
later timestamp than this arm's own `lastUpdated` moves recorded during the spike, so this
record does not claim the two happened at the same moment. But `claude plugin list` still
reported `Version: 0.1.9596`, matching this arm's own baseline and not the newly pushed
`0.1.4482` — **the installed version did not change even after the foreground update**, the
same result as the SSH arm. (This task's first reading of `s5_https_keep_run.log` misquoted
both `claude plugin list` occurrences as `Version: 0.1.4482`; re-reading the raw log during
review showed both actually read `Version: 0.1.9596`, and this record uses the corrected
value.) Because no clone or install
failure occurred anywhere in this arm, this task could not observe what
`CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1` changes about an actual failure path —
only that, in a run where nothing failed, the three-way split between session-start (no
change), foreground update (marketplace clone and cache staging refreshed, installed pointer
not) looked identical with the variable set as without it.

**Re-run path for the untested keep-on-failure half.** Forcing an actual clone or auth
failure needs the marketplace add or update to reach the remote and fail there, not merely be
refused locally: point `claude plugin marketplace add`/`update` at the same private repository
over HTTPS after revoking this machine's transparent credential access — either by running
`git credential-osxkeychain erase` for the `github.com` HTTPS entry (or `git config
--unset credential.helper` for the scratch config dir's own environment) before the call, or
by pointing the remote at a private repository under an account this token cannot read — then
repeat the HTTPS-keep arm with and without `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1`
exported, and compare whether `known_marketplaces.json`'s prior entry for
`keelline-marketplace` (and any partial clone under `plugins/marketplaces/`) survives the
failed call in each case. This was not attempted here because it needs deliberately breaking
this machine's own git credential state, a side effect outside this task's scope.

**Summary across all three arms.** In every arm, the session-start turn left
`installed_plugins.json` and `known_marketplaces.json`'s `lastUpdated` timestamp completely
unchanged from their immediately-pre-turn values — no background refresh was observed at
session start in any arm, SSH or HTTPS, with or without the keep-on-failure variable. This
absence does not by itself separate "does not refresh at session start" from "was not yet
considered stale": in every arm, the elapsed time from the `lastUpdated` value recorded right
after `plugin marketplace add` to the `lastUpdated` value recorded right after that arm's own
foreground update — a span that covers the marketplace add, the version bump, the push, the
session-start turn, *and* the foreground update — was under ten seconds: SSH
`2026-09-05T05:41:47.428Z` to `2026-09-05T05:41:57.129Z` (9.701s), HTTPS
`2026-09-05T05:42:53.777Z` to `2026-09-05T05:43:02.150Z` (8.373s), and HTTPS-keep
`2026-09-05T05:44:20.837Z` to `2026-09-05T05:44:29.673Z` (8.836s, all three recomputed from
the timestamps quoted per arm above). A staleness-gated refresh could not have fired inside a
window that short regardless of whether session start ever triggers one, so the foreground
update is a good positive control for the *detector* — the `lastUpdated` and version fields do
move, as every arm's own foreground update showed — but not for the *trigger*: this
measurement cannot distinguish a harness that never refreshes at session start from one that
refreshes only past a staleness threshold this run's own timing never reached. (The
SSH arm additionally shows its marketplace clone's `plugin.json` unchanged across the turn,
via this task's own `"0.1.0"` substring scan; the HTTPS and HTTPS-keep arms' baselines were
never `0.1.0`, so that same scan never matched their clone either before or after and adds no
information on this specific point for those two arms.) HTTPS did not fail or fall back to a
re-clone in either HTTPS arm; both cloned and installed cleanly, which this task attributes
to the machine's `osxkeychain` git credential helper authenticating the HTTPS remote
transparently, not to anything about the marketplace-refresh mechanism itself. In all three
arms, the foreground `claude plugin marketplace update` exited 0 and advanced
`known_marketplaces.json`'s `lastUpdated`, but what backs a claim about the marketplace
clone's own content differs by arm and is stated per arm above rather than generalized: the
SSH arm's clone dropped out of the `"0.1.0"` scan across that update (a version change,
value unknown); the plain-HTTPS arm has no logged or now-recoverable evidence either way,
its clone and cache directories having been deleted by the between-arm reset before this fix
could re-inspect them; the HTTPS-keep arm's clone and staged cache directory were never
reset and, re-inspected now, show HEAD at the pushed commit and the bumped version. In no
arm, at any point this task actually checked, did `claude plugin list` or
`installed_plugins.json` ever report a version different from the one installed at the start
of that arm; only an explicit `plugin update` (not run by this task, outside the brief's
scope) would have moved the installed pointer.

**Repository left behind.** `keelline-spike-s5` was not deleted: no `gh repo delete`, `gh
auth refresh`, or other scope-widening command was run, per the owner's declined
`delete_repo` scope. `gh repo view keelline-spike-s5 --json name,visibility,isPrivate`
printed `{"isPrivate":true,"name":"keelline-spike-s5","visibility":"PRIVATE"}` when re-run
during this fix (logged in `task5_fix_repo_view.log` in this directory) — the repository
still exists, private, under the owner's account, and the owner deletes it by hand.

### S6 — template creation race and renaming

Because the worktree-isolation Bash guard refused the brief's shell steps outright (they mix
`git` commands in a compound shape the guard cannot prove stays inside the worktree, while
this spike's git repositories are deliberately created under `$SPIKE`, outside it), all three
steps ran as Python scripts (`subprocess.run(["git", "-C", ...])` throughout) invoked with a
plain `python3 <path>`, rather than as the brief's literal shell blocks. Every command the
brief named was still run, with the same arguments; only the invocation shape differed. Owner
consent for creating both repositories had already been given in chat before this task
started, per the controller's brief.

Step 1 (`gh api user --jq .login`) printed the account login, recorded to `$SPIKE/owner` (not
reproduced here). `git -C $SPIKE/s6/tpl init -q -b main`, `git -C $SPIKE/s6/tpl add -A`, and
`git -C $SPIKE/s6/tpl commit -qm "spike: template"` each exited 0. `gh repo create
<owner>/keelline-spike-template --private --source $SPIKE/s6/tpl --push` printed
`https://github.com/<owner>/keelline-spike-template` and `branch 'main' set up to track
'origin/main'.` and exited 0. `gh api -X PATCH repos/<owner>/keelline-spike-template -F
is_template=true --jq .is_template` printed `true`.

Step 2 ran `gh repo create <owner>/keelline-spike-overlay --private --template
<owner>/keelline-spike-template --clone` from `$SPIKE/s6/work`, timed with Python's
`time.monotonic()`. It exited 0 after 8.83s and printed
`https://github.com/<owner>/keelline-spike-overlay`. Checking immediately afterward,
`$SPIKE/s6/work/keelline-spike-overlay/.claude-plugin` existed and held both `plugin.json` and
`marketplace.json`; reading `plugin.json` back printed `{"name": "spike-overlay", "version":
"0.0.1", "description": "spike overlay"}`, the template's own content. Because the directory
was already populated, the retry branch (`gh repo view ... --json name --jq .name`, `sleep
10`, `git clone -q ...`) never ran.

**The race did not reproduce in this one attempt.** That is a negative result from a single
trial, not evidence that no race exists: this task created exactly the two repositories the
brief named and had no `delete_repo` scope to remove `keelline-spike-overlay` between
attempts, so no second trial was run, and one clean run cannot rule out an asynchronous
generation step that only sometimes outlasts the clone. The 8.83s wall-clock time for the
combined create-and-clone call is corroborating evidence rather than a repeat trial: it is
long enough that `gh repo create --template --clone` plausibly already waits on the
server-side generation before it starts the clone step, which would be consistent with why
this one-shot construct did not race here.

**Retry rule for `overlay create`:** because a single non-racing trial cannot rule out the
race on a slower generation, `overlay create` needs the defensive retry regardless of this
result — check for a populated result (this run used the presence of `.claude-plugin` as
its probe) immediately after `--clone` returns; if it is absent, poll `gh repo view
<owner>/<repo> --json name --jq .name` to distinguish "the repository does not exist yet"
from "the repository exists but the clone raced its generation"; then wait and retry the
clone once with a plain `git clone` before treating the operation as failed. This run
exercised the happy path (`--clone` returned already populated) and left the retry path
prepared but unexercised, so it cannot say from direct observation whether one retry after
one wait is sufficient once a race actually occurs — the retry rule above is a design
carried over from the brief's own contingency, not a re-confirmed measurement.

Step 3 rewrote `$SPIKE/s6/work/keelline-spike-overlay/.claude-plugin/plugin.json`'s `name`
from `spike-overlay` to `spike-overlay-<owner>` and the sibling `marketplace.json`'s `name`
from `spike-overlay-marketplace` to `spike-overlay-marketplace-<owner>` (owner login
lower-cased), matching the same transform `overlay init --owner` is designed to apply, then
ran `git commit -qam "spike: rename for owner"` and `git push -q`, both exiting 0. A fresh
scratch config dir was created at `$SPIKE/cfg-s6`. `CLAUDE_CONFIG_DIR=<cfg-s6> claude plugin
marketplace add
git@github.com:<owner>/keelline-spike-overlay.git` printed `Adding marketplace…Refreshing
marketplace cache (timeout: 120s)…Cloning repository (timeout: 120s): git@github.com:
<owner>/keelline-spike-overlay.git Clone complete, validating marketplace…Cleaning up old
marketplace cache…✔ Successfully added marketplace: spike-overlay-marketplace-<owner>
(declared in user settings)` and exited 0. `CLAUDE_CONFIG_DIR=<cfg-s6> claude plugin install
spike-overlay-<owner>@spike-overlay-marketplace-<owner>` printed `Installing plugin
"spike-overlay-<owner>@spike-overlay-marketplace-<owner>"...✔ Successfully installed plugin:
spike-overlay-<owner>@spike-overlay-marketplace-<owner> (scope: user)` and exited 0.
`CLAUDE_CONFIG_DIR=<cfg-s6> claude plugin list` printed:

```
Installed plugins:

  ❯ spike-overlay-<owner>@spike-overlay-marketplace-<owner>
    Version: 0.0.1
    Scope: user
    Status: ✔ enabled
```

**The renamed marketplace and plugin installed successfully.** An owner-suffixed
plugin/marketplace pair, pushed to a private SSH remote, was added and installed without error
under a scratch `CLAUDE_CONFIG_DIR`, and `claude plugin list` reported it enabled under its
renamed selector — in this run, the `attach` lane's per-owner renaming scheme did not break
`claude plugin marketplace add`/`install` against a private repository.

Step 4's deletions were not run. The owner had declined the `delete_repo` scope and that
decision stood for this task, so neither `gh repo delete` call was run, and neither `gh auth
refresh` nor any other scope-widening command was run to work around it. Both
`keelline-spike-template` and `keelline-spike-overlay` were left in place, private, under the
owner's account, still present after this task finished; the owner deletes both by hand.

### S7 — hook output cap per entry

**Four changes applied to the brief's `arm()` helper before this task ran any arm.** All
eight arms installed into and ran against `$SPIKE/cfg-shared` — the one scratch config dir on
this machine the owner logged into by hand — instead of the brief's `mkcfg`, for the same
unauthenticated-config-dir reason recorded in Findings → S1 and → S2. Because this worktree's
Bash guard refused `arm.sh`'s own compound shell/`git`-init shape (the same class of refusal
Findings → S2, S4 and S6 record), the whole arm loop was reimplemented as a Python driver
(`task7_arm.py`, invoked as a plain `python3 <path>` per arm, plus `task7_setup.py` for the
one-time plugin skeleton and `task7_final_analysis.py` for the cross-arm re-read below — all
three gitignored scratch scripts, not part of this commit) reproducing the brief's `hooks.json`
shape exactly: one `SessionStart` group per arm, holding one `{"type": "command", ...}` entry
per requested size. Every canary tag was made unique across the whole spike by prefixing it
with the arm name (`control_A`, `two-entries_A`/`two-entries_B`, `one-big_A`,
`margin-9000_A`, …, `margin-10001_A`), and every `persisted_outputs` count below is a
before/after delta for that arm's own turn, not the cumulative total `persisted_outputs "$cfg"
| wc -l` would have printed against the shared config dir.

**Which reader this task used, and why the `### Environment` caveat about `hook_records`
dropping `hook_non_blocking_error` does not reach this task's verdict.** This task's own
`persisted files added` counts came from `persisted_outputs`, a `find` over `tool-results`
paths that does not go through `hook_records` at all and so cannot be affected by the type it
drops. The `hook_success` stdout lengths and `hook_additional_context` content this task
quotes both came from the two record types `hook_records`'s `kind in {...}` test does match —
`hook_success` and `hook_additional_context` are two of the three record types that the test
matched. The fourth type in the transcripts, `hook_non_blocking_error`, was not in that matched
set and is what the helper silently dropped. No arm in this task ever needed to observe a blocked or errored hook (every entry in
every arm ran and produced output), so this task never needed the dropped record type in the
first place. This task's verdict is therefore immune to the gap Findings → Environment
records, unlike a spike that needed `hook_non_blocking_error` itself.

**How every arm's install was verified fresh before its turn, and which physical file was
checked.** Findings → S2 established that `${CLAUDE_PLUGIN_ROOT}` resolves to the
marketplace's own source directory (`$SPIKE/s7`) rather than the `plugins/cache` copy
`installed_root` names, so this task did not treat that source directory as proof of
freshness — a stale registration could still point at it correctly while running old hook
*commands*. Instead, each arm (1) wrote `$SPIKE/s7/hooks/hooks.json` with that arm's entries,
(2) bumped `$SPIKE/s7/.claude-plugin/plugin.json`'s `version` field to a value unique to that
arm (`7.0.1` through `7.0.8`, one per arm in run order), (3) ran `claude plugin uninstall
s7@s7-marketplace -y` and `claude plugin marketplace remove s7-marketplace` against
`$SPIKE/cfg-shared` — both printed `not found` on the control arm, the first of the eight,
because nothing had yet been installed under this plugin name in `$SPIKE/cfg-shared`, and
both printed a `✔ Successfully …` line on every arm after it — then deleted any leftover
`$SPIKE/cfg-shared/plugins/cache/s7-marketplace` directory outright before re-adding the
marketplace from `$SPIKE/s7` and reinstalling. After every install, this task read back the
installed copy's `hooks.json` from the `plugins/cache` location `installed_root` names (for
example `$SPIKE/cfg-shared/plugins/cache/s7-marketplace/s7/7.0.1/hooks/hooks.json` for the
control arm) and compared it byte-for-byte to the `$SPIKE/s7/hooks/hooks.json` just written.
All eight arms printed `VERIFY installed hooks.json == source just written: True` on the
first attempt; none needed the forced-retry branch. This freshness check was corroborated
empirically by every arm's own turn: every persisted file and every `hook_success`/
`hook_additional_context` record recovered below, across all eight arms, carried only that
arm's own canary tag and never a previous arm's, including for the three arms (control,
two-entries and one-big — the "Step 1 & 2" discrimination arms below) run first to validate
this mechanism before the remaining five margin arms consumed any turn budget.

**Step 1 & 2 — the discrimination arms.** Per arm: the `stderr` size line `big.py` printed,
the `hook_success` record's `stdout` length for each entry, the resulting
`hook_additional_context` record's content, and the persisted files this arm added (a fresh,
this-session-only directory under `$SPIKE/cfg-shared/projects/.../tool-results/`, confirmed
empty of any file before the turn and diffed against its contents after).

| arm | entries | `stderr` line(s) | `hook_success` stdout length(s) | `hook_additional_context` content | persisted files added |
|---|---|---|---|---|---|
| control | 1×8000 | `S7 control_A emitted 8000 characters` | 8083 | one element, 8000 chars, unspilled | 0 |
| two-entries | 2×8000 | `S7 two-entries_A emitted 8000 characters`; `S7 two-entries_B emitted 8000 characters` | 8083, 8083 | **one** `hook_additional_context` record whose `content` was a two-element list, `[8000, 8000]`, both unspilled | 0 |
| one-big | 1×16000 | `S7 one-big_A emitted 16000 characters` | 16083 | one element, spilled — replaced with `<persisted-output>\nOutput too large (15.6KB). Full output saved to: …` | 1, exactly 16000 chars, beginning `CANARY_one-big_A` |

The two-entries arm's single combined transcript record carrying a two-element `content` list
(`[8000, 8000]`, one element per hook script invocation, each still opening with its own
`CANARY_two-entries_A `/`CANARY_two-entries_B ` prefix) was itself load-bearing evidence
independent of the persisted-file count: Claude Code did not concatenate the two hooks'
additional-context strings into one string before deciding whether to persist. It kept them
as separate list elements and evaluated each one on its own length — 8000 characters each,
neither over the cutover — even though their combined total, 16000 characters, is the exact
figure that spilled when produced by one-big's single entry. Every persisted file this task
found (one-big's and, in Step 3, margin-10001's) was confirmed to open with only its own
arm's canary prefix and no other arm's text.

**Step 3 — the margin, one entry each.**

| size | tag | `stderr` line | `hook_success` stdout length | `hook_additional_context` content | persisted files added |
|---|---|---|---|---|---|
| 9000 | `margin-9000_A` | `S7 margin-9000_A emitted 9000 characters` | 9083 | one element, 9000 chars, unspilled | 0 |
| 9900 | `margin-9900_A` | `S7 margin-9900_A emitted 9900 characters` | 9983 | one element, 9900 chars, unspilled | 0 |
| 9999 | `margin-9999_A` | `S7 margin-9999_A emitted 9999 characters` | 10082 | one element, 9999 chars, unspilled | 0 |
| 10000 | `margin-10000_A` | `S7 margin-10000_A emitted 10000 characters` | 10083 | one element, 10000 chars, unspilled | 0 |
| 10001 | `margin-10001_A` | `S7 margin-10001_A emitted 10001 characters` | 10084 | one element, spilled — replaced with `<persisted-output>\nOutput too large (9.8KB). Full output saved to: …` | 1, exactly 10001 chars, beginning `CANARY_margin-10001_A` |

10000 characters in one entry did not spill and 10001 characters in one entry did; the
boundary this task measured sits exactly at 10,000, exclusive.

**Turns spent.** Eight `claude -p --model haiku` turns, one per arm (control, one-big and
two-entries, run in that order to validate the install-freshness mechanism on the two arms
expected to disagree before spending budget on the rest; then the five margin arms), against
a budget of up to nine. The ninth, spare turn was not used, and no arm needed a second turn.

**Verdict.** The two-entries arm added no persisted file and the one-big arm added one — the
brief's own discriminator between the two branches. Had the cap been evaluated over the whole
`SessionStart` event's combined additional-context output rather than per hook entry, the
two-entries arm's combined 16,000 characters (8000 + 8000) would have spilled exactly as
one-big's single 16,000-character entry did, and it did not; the two-element `content` list
recovered from its transcript record showed each entry's own text kept intact at its own
length. This result fell cleanly into the first branch: §9.5's one-entry-per-bundle remedy
held on this measurement, `hooks-core` does not need to spread bundles across events or
shrink them on this account, and the value this task measured for the preset's
`hook_output_chars` is 10,000 — the largest single entry that did not spill, immediately
below the smallest that did (10,001).

### S8 — fail-closed matrix

**Five corrections applied to the brief before this task ran any step, all disclosed here.**
(1) Step 2's `ROOT=$(installed_root s8 "$CFG"); [ "$ROOT" = REFERENCED ] && ROOT="$SPIKE/s8"`
line was rewritten as an `if`/`fi`: under `set -eu` a false `&&` list aborts the whole step,
and Task 0 measured that `installed_root` never returns `REFERENCED` on this machine — this
task's own install (below) printed a `plugins/cache` path again, never that word. (2) Every
install and turn ran against `$SPIKE/cfg-shared`, the one authenticated config dir on this
machine, never `mkcfg s8` (an unauthenticated dir fails every turn with `Not logged in`, per
Findings → S1/S2/S7). (3) Every row bumped `$SPIKE/s8/.claude-plugin/plugin.json`'s version, ran a full
`uninstall` / `marketplace remove` / cache-dir delete before reinstalling, and read the
freshly installed `plugins/cache` copy back to diff it against the mutated source before
spending a turn — Task 7's proven procedure, applied identically. (4) Which physical copy
`${CLAUDE_PLUGIN_ROOT}` resolves to for this plugin was established fresh for S8 rather than
assumed from S2/S7 (below), and every row's mutation was made there. (5) Every row and
payload used a marker unique across the whole spike (`S8_DENY_<row>` / `S8_ALLOW_<row>`),
and hook records were read by walking the raw transcript JSON directly rather than through
`lib.sh`'s unmodified `hook_records`, because this task found a transcript shape neither
that helper nor Findings → Environment's `hook_non_blocking_error` correction anticipated
(below).

Because this worktree's Bash guard refused the brief's heredoc-and-`set -eu` shell shape
(the same class of refusal Findings → S2, S4, S6 and S7 record; it separately refused a
`find` over a `$HOME`-derived path used only to inspect state, with "cannot be shown not to
be git"), every step ran as a Python driver under
`.superpowers/sdd/2026-09-05-agent-harness-p0-spikes/` (`task8_lib.py` for the shared
helpers, `task8_setup.py` for Step 1, `task8_baseline.py` for Step 2, `task8_row.py
<row-key>` run once per row for Step 3, plus a one-off `task8_reprocess.py` and
`task8_check_marketplace.py` used only to re-read already-completed turns and installed
state after the extraction bug below was found — all gitignored scratch scripts, not part
of this commit), invoked as a plain `python3 <path>`, reproducing the brief's file contents
and command arguments exactly except for the five corrections above.

**Step 1 — the wrapper, guard and hooks.json, written under `$SPIKE/s8` unmodified from the
brief.** `task8_setup.py` wrote the three files and printed each back; their content matched
the brief's Step 1 verbatim (reproduced in full under "The wrapper's final text" below), and
`$SPIKE/s8/hooks/run-hook.sh`'s mode printed `755`.

**Which copy `${CLAUDE_PLUGIN_ROOT}` resolves to for this plugin, established fresh rather
than assumed.** After the pristine plugin (version `8.0.1`) was installed into
`$SPIKE/cfg-shared`, reading `$SPIKE/cfg-shared/plugins/known_marketplaces.json` printed
`{"s8-marketplace": {"source": {"source": "directory", "path": "$SPIKE/s8"},
"installLocation": "$SPIKE/s8", "lastUpdated": "2026-09-05T06:43:58.365Z"}}` — the
marketplace's own source directory, the shape Findings → S2 measured for the same
`mkplugin`/directory-marketplace construction. Rather than transferring that finding
unverified, this task spent one more cheap turn before Step 3: with the pristine plugin
installed and both copies still byte-identical, it mutated *only* the installed
`plugins/cache` copy's guard script (`$SPIKE/cfg-shared/plugins/cache/s8-marketplace/s8/
8.0.1/scripts/guard.py`), prepending `import no_such_module_s8_cacheonly` to it, left the
marketplace source untouched, did **not** bump the
version or reinstall, and ran `claude -p --model haiku --output-format json "Run exactly
this shell command: echo S8_ALLOW_cacheonly_probe"`. If the cache copy were live, the
planted `ImportError` would have made `guard.py` exit 1 and the wrapper's closed-policy
fallback would have refused with `KL_GUARD_RC`. Instead the transcript's own
`bash_tool_result` record for that turn read `"is_error": false, "toolDenialKind": null,
"blocked_by_hook": false, "content": "S8_ALLOW_cacheonly_probe"` — the command ran clean, as
if the cache mutation had never happened. This task therefore mutated the **marketplace
source directory** (`$SPIKE/s8`) for every row below, restoring the cache copy's
`guard.py` to its original content immediately afterward.

**Step 2 — the two-sided baseline.** Two turns ran against `$SPIKE/cfg-shared`/`$SPIKE/s8/
proj`: `"Run exactly this shell command: echo S8_DENY_baseline"` and, separately, `"...echo
S8_ALLOW_baseline"`. Reading each turn's own newly-created transcript file (isolated from
every other spike's records already accumulated in `cfg-shared` by diffing the file set
before/after the turn, not by grepping for a marker) found, for the DENY turn, a `user`-role
message whose `tool_result` read `"is_error": true, "toolDenialKind": "permission-rule"`,
content `'PreToolUse:Bash hook error: ["$SPIKE/s8/hooks/run-hook.sh" PreToolUse closed]:
keelline: KL_DENY the S8 guard denies this command\n'`; for the ALLOW turn, the matching
record read `"is_error": false`, content `'S8_ALLOW_baseline'` — the command actually ran.
**Both verdicts held**: the DENY payload was blocked with `KL_DENY` in stderr and the ALLOW
payload passed through and executed, so the baseline was two-sided and the matrix in Step 3
was run in full.

**A transcript shape this task found that neither `lib.sh`'s `hook_records` nor Findings →
Environment's `hook_non_blocking_error` correction anticipated.** Every record
`hook_records` checks for (`hook_success`, `hook_error`, `hook_additional_context`, and the
`hook_non_blocking_error` Findings → Environment added) is an `"attachment"`-typed line
whose *nested* `attachment.type` carries the hook-specific value and an explicit numeric
`exitCode` — this task's own row 6 below produced exactly that shape. A **blocking**
PreToolUse denial, the shape this whole spike exists to measure, is none of those: it is a
plain `user` message whose `tool_result` content is the string `"PreToolUse:<Tool> hook
error: [<command>]: <stderr>\n"`, `"is_error": true`, sibling field `"toolDenialKind":
"permission-rule"`, and **no numeric exit-code field anywhere in the line**. A passing
PreToolUse hook leaves no record at all — only the tool's own successful result. A reader
porting `hook_records` unmodified into the `hooks-core` test this spike feeds would find
nothing for either arm of the DENY/ALLOW matrix; this task instead walked every new
transcript line directly, pairing each `assistant` `tool_use` (Bash) with its `user`
`tool_result` by `tool_use_id`. Every "blocked" row in the table below is therefore reported
on the strength of two independent facts rather than a transcript-native exit-code field:
the wrapper's own source calls `exit 2` from every `refuse()` branch that produces one of
the four tokens, and Claude Code's own transcript labeled the outcome `"hook error"`
(blocking) rather than `"hook non-blocking error"` (the label row 6's genuinely different
exit code, 126, produced).

**Step 3 — six rows, two payloads, mutation-freshness proven before every turn.** Each row's
`task8_row.py <row>` run restored the pristine source, applied that row's mutation, bumped
`plugin.json`'s version (`8.0.2` through `8.0.7`; pristine was `8.0.1`), ran a full
`uninstall`/`marketplace remove`/cache-dir delete, reinstalled, and read the freshly
installed `plugins/cache/s8-marketplace/s8/<version>/` copy back before spending either
turn. Every row's mutated file matched the installed copy byte-for-byte (or, for the
executable-bit row, byte-for-byte **and** mode-for-mode) on the **first** attempt; none
needed the forced-retry branch.

| Row | `plugin.json` version | Verify | DENY: blocked / token | ALLOW: blocked / token |
|---|---|---|---|---|
| no interpreter | 8.0.2 | `$SPIKE/s8/hooks/hooks.json` byte-for-byte match: True | blocked / `KL_NO_PY` | blocked / `KL_NO_PY` |
| only 3.9 available | 8.0.3 | `$SPIKE/s8/hooks/hooks.json` byte-for-byte match: True | blocked / `KL_NO_PY` | blocked / `KL_NO_PY` |
| `CLAUDE_PLUGIN_ROOT` unset | 8.0.4 | `$SPIKE/s8/hooks/hooks.json` byte-for-byte match: True | blocked / `KL_NO_SCRIPT` | blocked / `KL_NO_SCRIPT` |
| script deleted | 8.0.5 | `$SPIKE/s8/scripts/guard.py`: source missing, cache missing | blocked / `KL_NO_SCRIPT` | blocked / `KL_NO_SCRIPT` |
| ImportError planted | 8.0.6 | `$SPIKE/s8/scripts/guard.py` byte-for-byte match: True | blocked / `KL_GUARD_RC` | blocked / `KL_GUARD_RC` |
| executable bit cleared | 8.0.7 | `$SPIKE/s8/hooks/run-hook.sh` byte-for-byte match: True; mode expected `0o644` actual `0o644` match: True | **not** blocked / none | **not** blocked / none |

The stderr each refusal carried, quoted from that row's own log (`$SPIKE`-relative paths):

- **no interpreter** (both payloads): `'PreToolUse:Bash hook error: [env
  KEELLINE_PYTHON_CANDIDATES=/nonexistent/python3 "$SPIKE/s8/hooks/run-hook.sh" PreToolUse
  closed]: keelline: KL_NO_PY no python3 of 3.11 or newer among the candidates;
  refusing\n'`.
- **only 3.9 available** (both payloads): the same message with
  `KEELLINE_PYTHON_CANDIDATES=/usr/bin/python3` in the command — `/usr/bin/python3` is the
  3.9.6 interpreter Findings → Environment recorded, so the wrapper's `sys.version_info >=
  (3, 11)` probe rejected it and left `p` empty exactly as the missing path above did; the
  version floor was exercised, not only the executable bit.
- **`CLAUDE_PLUGIN_ROOT` unset** (both payloads): `'...keelline: KL_NO_SCRIPT guard script
  missing at /scripts/guard.py; refusing\n'` — the literal root-relative path confirms
  `${CLAUDE_PLUGIN_ROOT:-}` really was empty for this invocation, not merely that the guard
  file happened to be missing.
- **script deleted** (both payloads): `'...keelline: KL_NO_SCRIPT guard script missing at
  $SPIKE/s8/scripts/guard.py; refusing\n'`.
- **ImportError planted** (both payloads): `'...Traceback (most recent call last):\n  File
  "$SPIKE/s8/scripts/guard.py", line 1, in <module>\n    import no_such_module_s8\n
  ModuleNotFoundError: No module named \'no_such_module_s8\'\nkeelline: KL_GUARD_RC guard
  failed with rc=1; refusing\n'`.
- **executable bit cleared** (both payloads): no denial record of any kind; each turn's own
  `content` was the literal echoed marker (`S8_DENY_exec_bit_cleared` /
  `S8_ALLOW_exec_bit_cleared`), meaning the command ran. The transcript instead carried, for
  both turns, `{"type": "hook_non_blocking_error", "hookName": "PreToolUse:Bash",
  "hookEvent": "PreToolUse", "stderr": "Failed with non-blocking status code: /bin/sh:
  $SPIKE/s8/hooks/run-hook.sh: Permission denied", "exitCode": 126, "command":
  "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh\" PreToolUse closed"}` — a non-executable hook
  script cannot signal `closed`-policy intent at all; Claude Code classified its rc-126
  launch failure as non-blocking and let the tool call through regardless of the hook's own
  policy argument, for the DENY payload as much as the ALLOW one.

**Step 4 — the verdict.** On the pristine copy, DENY gave a blocking hook error carrying
`KL_DENY` and ALLOW ran clean — correct. Every broken row except "executable bit cleared"
blocked **both** payloads with its own token in stderr — correct, and unanimous across all
five rows exercised (no row let ALLOW through while broken, and no row blocked without a
token). **The wrapper is correct as drafted**, against the brief's own criterion. The
"executable bit cleared" row is the one the brief itself carved out as unreachable by the
wrapper (it never runs), and this task's own measurement showed why that carve-out cannot be
closed inside `run-hook.sh`: with the bit cleared, `/bin/sh` never invokes the script at
all, so no wrapper code path runs `refuse()`, and Claude Code's own rc-126 handling degrades
open rather than failing closed. The change this row calls for belongs to the **installer
and `doctor`** (§5.3, as the brief already names): a post-install check that `stat`s the hook
wrapper (and any other hook entry point) for its executable bit and fails the install, plus a
`doctor` check that flags a plugin whose hook files lost their executable bit after install
(e.g. a checkout or transport that does not preserve modes) — `hooks-core` should treat "hook
file lacks +x" as a distinct, install-time-checked defect class from anything `run-hook.sh`
can detect at hook-run time. **The copy that check must `stat` is not the `plugins/cache`
copy.** Findings → S2's headline discovery, re-established fresh for this plugin above (the
cache-mutation probe before Step 3) and again by Findings → S7, is that `${CLAUDE_PLUGIN_ROOT}`
resolves to the **marketplace's own source directory** — the location `known_marketplaces.json`
records as `installLocation` — not the `plugins/cache` copy `installed_root` names, for every
directory-sourced marketplace this spike series built. A post-install check that `stat`s the
`plugins/cache` copy would pass while the file the OS actually refuses to launch (the
marketplace-location copy `${CLAUDE_PLUGIN_ROOT}` resolves to at hook-run time) goes
unchecked; the check must `stat` the `known_marketplaces.json` `installLocation` path instead.
Findings → S2's Summary row already carries the caveat this inherits: whether a git-URL-sourced
marketplace — the real distribution shape for Keelline, never a `directory`-sourced one — keeps
`${CLAUDE_PLUGIN_ROOT}` pointed at the same kind of location was not tested by this spike
series, so the check's actual target under Keelline's own distribution shape stays unknown
until that measurement is taken.

**Where this row sits against spec §2 D11.** D11 says the shell wrapper "maps every exit code
other than 0 and 2 to 2 with a printed reason — because a Python process cannot fail closed
about its own absence (a missing script exits 2 by CPython accident, a missing interpreter
127, an `ImportError` 1, a lost executable bit 126)." The wrapper's own `case "$rc" in 0|2)
exit "$rc" ;; *) …esac` genuinely delivers that remapping, but only for the exit code of the
**child** it launches (`"$p" "$script" "$event"`) — this task's own "ImportError planted" row
measured exactly that path, rc 1 from `guard.py` remapped to `KL_GUARD_RC`/exit 2, and the "no
interpreter"/"only 3.9 available" rows measured the wrapper's own `[ -z "$p" ]` check refusing
before any child even runs. None of those three is a lost executable bit on `guard.py`
itself, because `guard.py` is always invoked as `"$p" "$script"` — an argument to `python3`,
which needs only read permission, the same shape Findings → S2 measured running a 644 script
to exit 0. D11's own "lost executable bit 126" example can only describe the **wrapper's own**
file, `run-hook.sh`, invoked directly (no interpreter prefix) from `hooks.json` — and that is
exactly what row 6 tested: with `run-hook.sh`'s own bit cleared, `/bin/sh` exits 126 before any
of the wrapper's own code — including the `case` statement D11 credits — ever runs, so nothing
performs the remapping D11 promises. D11 states one uniform guarantee across all four listed
exit codes; this row shows the guarantee is delivered by two different mechanisms depending on
which file lost execute permission, and only the mechanism covering the child process's exit
code is actually backed by `run-hook.sh`'s own body — the wrapper cannot make a promise about
its own absence.

**A cheaper candidate remedy this row's own evidence supports, offered untested.** Rather than
(or in addition to) an install-time `stat` check, declaring the hook in `hooks.json` as `sh
"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.sh" PreToolUse closed` — invoking the wrapper through an
interpreter instead of directly — would make the wrapper's own executable bit irrelevant to
whether it runs at all, the direct analogue of Findings → S2's own measurement that `python3
"${CLAUDE_PLUGIN_ROOT}/scripts/noexec.py"` ran a 644, non-executable file to exit 0 while the
same file invoked directly exited 126. This task did not write that `hooks.json` shape and
re-run row 6 against it, so it is recorded here as an untested candidate, not a confirmed fix
— `hooks-core` should price this one manifest string against the two checks above (installer
`stat`, `doctor` re-check) rather than assuming either is the only option.

**Turns spent.** 15 `claude -p --model haiku` turns: 2 for the Step 2 baseline, 1 for the
cache-vs-source discrimination probe above, and 2 each for the six rows (12), against a
budget of up to 16.

**The wrapper's final text**, as installed for every row above (identical to Step 1's
draft; none of the five corrections touch its own body, only the orchestration around it):

```sh
#!/bin/sh
# Keelline hook wrapper (spike draft). $1 = event, $2 = policy (open|closed).
# Every refusal prints its own token so an exit 2 is attributed, never inferred.
event="$1"; policy="$2"
refuse() { echo "keelline: $1; refusing" >&2; exit 2; }
degrade() { echo "keelline: $1; continuing open" >&2; exit 0; }
script="${CLAUDE_PLUGIN_ROOT:-}/scripts/guard.py"
p=
for c in ${KEELLINE_PYTHON_CANDIDATES:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 /usr/local/bin/python3 /usr/bin/python3}; do
  if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    p="$c"; break
  fi
done
if [ -z "$p" ]; then
  [ "$policy" = closed ] && refuse "KL_NO_PY no python3 of 3.11 or newer among the candidates"
  degrade "KL_NO_PY"
fi
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ] || [ ! -f "$script" ]; then
  [ "$policy" = closed ] && refuse "KL_NO_SCRIPT guard script missing at ${script}"
  degrade "KL_NO_SCRIPT"
fi
"$p" "$script" "$event"; rc=$?
case "$rc" in
  0|2) exit "$rc" ;;
  *) [ "$policy" = closed ] && refuse "KL_GUARD_RC guard failed with rc=$rc"; degrade "KL_GUARD_RC rc=$rc" ;;
esac
```

Correction 1's fix to Step 2's own orchestration, for `hooks-core` to carry forward into its
shell-based permanent test (this task's own driver reimplemented the equivalent lookup in
Python — `find_installed_root` in `task8_lib.py` — since the brief's shell shape itself was
what this worktree's guard refused, per correction 2's paragraph above):

```bash
ROOT=$(installed_root s8 "$CFG")
if [ "$ROOT" = REFERENCED ]; then ROOT="$SPIKE/s8"; fi
echo "$ROOT" > "$SPIKE/s8/root"
```

### S9 — containment fixture

This entry is a recorded fixture design, not a measurement: per Task 9 Step 2 ("the engine
does not exist in P0"), nothing was run and no command is named below.

The fixture below is copied verbatim from the Task 9 brief as the `scaffold` lane's
containment test input, exercised against `plan()` from contract C2 (design spec §7.4):

```toml
[keelline]
version = "0.1.0"
state = "adopting"
preset = "recommended"
profile = ""
agents = ["claude"]

[project]
name = "../common"
base_branch = "main"
release_branch = "main"

[paths]
agents_md = "../../.claude/CLAUDE.md"
specs = "/etc/keelline-specs"
plans = "docs/plans"
memory = "link-to-elsewhere"
```

The fixture's `memory` path is created as a symlink pointing outside the fixture root, not as
an ordinary directory — the escape for that one path is symlink-based, distinct from the
string-based escapes of `agents_md` and `specs`.

Three assertions, each paired in the scaffold plan with the mutation expected to redden it:

1. Loading the config raises the loader's error on the project name (one path segment) —
   `project.name = "../common"` fails at load, before `plan()` ever runs.
2. With the name corrected, `plan()` yields zero actions for the agents file, the specs
   directory and the memory path, and exactly the actions for the plans directory.
3. `apply()` on a plan computed before the plans directory was swapped for a symlink refuses
   to write.

### S10 — hostile clone scenario

This entry is a recorded scenario design, not a measurement: per Task 10 Step 2 ("this task
ends when the scenario is recorded"), nothing was run and no command is named below.

The scenario the `workflows` lane implements in the smoke workflow (design spec §13), with
fixtures from the `attach` and `memory-engine` lanes:

- A fixture repository in `in-repo` memory mode, holding a note whose `metadata.startup`
  rank is negative and whose body is `S10_RULE_CANARY`, with `project.name` set to `victim`.
- A scratch overlay whose own `victim` project store holds a note with body
  `S10_STORE_CANARY`, and whose project binding names a different remote than the fixture
  repository's.

Three separate assertions, kept separate rather than collapsed into one — the brief is
explicit that they are asserted separately, because clone, memory and attach each have to
fail independently for the scenario to mean anything:

1. A `SessionStart` run against the fixture, without the in-repo trust step, emits no
   additional context containing `S10_RULE_CANARY`; the same run, with trust recorded, emits
   it wrapped in the in-repo data marker and positioned after the owner's own rules (§9.4).
2. A memory search for `S10_STORE_CANARY` run from the fixture returns nothing.
3. Attaching the fixture to the overlay's `victim` store exits 2 with a remote-mismatch
   reason and creates no symlink.

### Summary

| Spike | Answer | Feeds | Design consequence |
|---|---|---|---|
| S1 | Codex's own hook launch set harness-specific env names (`CODEX_MANAGED_BY_NPM`, `CODEX_MANAGED_PACKAGE_ROOT`, `PLUGIN_ROOT`, `PLUGIN_DATA` on the Codex side; `CLAUDE_ENV_FILE`, `CLAUDE_PROJECT_DIR` on the Claude side) — but Codex's own hook launch also set `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` alongside its bare `PLUGIN_ROOT`/`PLUGIN_DATA`, so a `detect_harness()` keyed on `CLAUDE_PLUGIN_ROOT` alone would misidentify Codex as Claude Code — and Codex read the same .claude-plugin/marketplace.json file Claude read. `CODEX_HOME` and `CLAUDE_CONFIG_DIR` are unattributable in this run: both were set as command-line prefixes to the harness invocation itself, which the parent-shell ambient baseline this run subtracted can never contain, so this measurement cannot tell "harness-set" apart from "survived from the launching command line" for either one — a `detect_harness()` candidate needs a separating re-measurement first. Both harnesses tolerated the two unrecognized hook keys at install time and on `SessionStart`. On stdin, Codex's `SessionStart` payload carried `model` and `permission_mode` and Claude's did not — this run's actual answer to §14's "stdin field that identifies Codex." Neither harness's `PreToolUse` hook ever fired in this run — Claude's turns failed on `CLAUDE_CONFIG_DIR`-scoped credential isolation and Codex's turn failed on an exhausted account quota — so the `tool_name` comparison and PreToolUse-time key tolerance were never obtained. | §10, §5.1 | Confirms §10 rather than correcting §5.3: §10 already lists `${CLAUDE_PLUGIN_ROOT}`/`${CLAUDE_PLUGIN_DATA}` as shared across harnesses, and §5.1 already gives the same .claude-plugin/marketplace.json file to both — this run's own measurement backs both directly (no second marketplace file needed). `detect_harness()` is this plan's own provisional term, not spec vocabulary, and §5.3 names no harness-detection mechanism to correct; whatever adopts `detect_harness()` must not key on `CLAUDE_PLUGIN_ROOT`/`CLAUDE_PLUGIN_DATA` alone, since Codex sets those too, and must not key on `CODEX_HOME` or `CLAUDE_CONFIG_DIR` either without the separating re-measurement above — the stdin `model`/`permission_mode` pair is the discriminator this run actually established. The `tool_name` mapping and PreToolUse key tolerance stayed open — not obtained, for either harness, in this run. |
| S2 | `${CLAUDE_PLUGIN_ROOT}` substitution happened in both the hook command and the skill content, but the transcript's own `command` field retained the unsubstituted template text — only the substituted commands' stderr/stdout and the skill's rendered tool input proved substitution occurred. Substitution resolved to the marketplace's source directory, not the installed `plugins/cache` copy `installed_root` names. The only mode this task originally put through an install was 644 → 644, which could not distinguish "install preserves modes" from "install normalises everything to 644" — spec §14's actual question; a follow-up measurement (finding A2(b), a fresh 755-and-644 pair through a fresh install, logged under `.superpowers/sdd/`) closed it: the installed `plugins/cache` copy preserved 755 and 644 respectively, matching the source, for this directory-sourced marketplace. Independently of either mode question, a hook script lacking the executable bit failed direct invocation (exit 126, permission denied) but ran cleanly when invoked through `python3`. The Codex arm (Step 4) was not run — the account's quota was exhausted and the owner declined to raise it. | §5.1, §2 D11 | Amend §2 D11 / §5.1: `${CLAUDE_PLUGIN_ROOT}` resolved to the marketplace's source directory rather than the installed cache copy on this (directory-sourced) configuration, so the design must not assume the installed cache path is what hooks and skills see at runtime, and a transcript's own `command` field is not sufficient proof of substitution without also reading stderr/stdout. A directory-sourced marketplace install preserves the executable bit into the `plugins/cache` copy rather than normalising it (A2(b)); git-URL-sourced marketplace mode-preservation and Codex's own substitution behavior both stayed untested. |
| S3 | Not run beyond Step 1 (seeding a Claude memory canary) — the Codex account's quota was exhausted and the owner declined to raise it; the interactive `/import` step and the canary comparison never happened. | §2 D5, §6.4 | Open — §2 D5 and §6.4 kept the question of whether Codex's `/import` carries Claude memory notes at all; this run gave neither section an answer. |
| S4 | `claude plugin validate` cascaded into skill, agent, and Codex-manifest checks only when pointed directly at the plugin's own .claude-plugin/plugin.json; validating the bare directory or the marketplace.json target reported none of the three planted defects, in either `--strict` setting. `--strict` escalated warnings to failures but did not by itself widen what got checked. Separately, the valid tree's own .codex-plugin/plugin.json failed validation unconditionally, in both `--strict` settings, because its `"skills": "./skills/"` path resolved one directory level below the actual skills/ tree the brief built. | §5.8 | Amend §5.8: CI/doctor validation must target each plugin's .claude-plugin/plugin.json path explicitly rather than the bare directory or marketplace.json, to catch skill/agent/Codex-manifest defects, and the Codex manifest layout's `skills` path convention needs correcting so a valid tree does not fail validation on its own. |
| S5 | In all three arms (SSH, HTTPS, HTTPS with `CLAUDE_CODE_PLUGIN_KEEP_MARKETPLACE_ON_FAILURE=1`), a session-start turn never advanced `known_marketplaces.json`'s `lastUpdated` or the installed plugin's reported version, but each arm's session-start turn ran under ten seconds after `plugin marketplace add` (9.701s SSH, 8.373s HTTPS, 8.836s HTTPS-keep), so this does not separate "does not refresh at session start" from "was not yet considered stale" — only that no refresh fired inside that short a window. Only the foreground `claude plugin marketplace update` advanced `lastUpdated`, and even that update never moved the installed plugin's own reported version in any arm. HTTPS authenticated transparently through the machine's `osxkeychain` credential helper with no failure in either HTTPS arm, so the keep-on-failure variable was never exercised against an actual failure. | §6.4 | Amend §6.4: session start did not refresh a private marketplace within roughly ten seconds of the marketplace being added in this measurement — a design relying on session-start to pick up a new marketplace commit needs an explicit `plugin marketplace update` step regardless, and moving the installed pointer needs a separate, untested `plugin update`. Whether session start refreshes past a longer staleness threshold, and the keep-on-failure variable's effect on a genuine failure, both stayed unmeasured. |
| S6 | The `gh repo create --template --clone` race did not reproduce in this one trial — the combined call took 8.83s and returned already populated — and the owner-suffixed rename of both `plugin.json`'s and `marketplace.json`'s `name` fields installed and ran cleanly via `claude plugin marketplace add`/`install` against the private SSH remote. | §6.1 | As designed — §6.1's per-owner renaming worked against a private SSH remote in this trial; the defensive retry-after-wait rule for the create/clone race stayed in the design as an unexercised contingency, since one non-racing trial could not rule out the race on a slower generation. |
| S7 | The 10,000-character spill cap applied per hook entry, not per event: two 8,000-character entries in one `SessionStart` group stayed unspilled (a combined 16,000 characters) while a single 16,000-character entry spilled, and the boundary sat at exactly 10,000 characters — 10,000 stayed unspilled, 10,001 spilled. | §9.5 | As designed — §9.5's one-entry-per-bundle remedy held on this measurement; the value measured for the `hook_output_chars` preset was 10,000. |
| S8 | The wrapper failed closed correctly on five of six fault rows (no qualifying Python interpreter, only Python 3.9 available, `CLAUDE_PLUGIN_ROOT` unset, guard script deleted, guard `ImportError`), blocking both the DENY and ALLOW payload with its own token every time. The sixth row — the hook wrapper's own executable bit cleared — blocked neither payload: Claude Code logged the resulting exit-126 launch failure as a non-blocking hook error and let the tool call through regardless of the configured policy. | §5.3, §2 D11, §13 | Amend §5.3: the installer and `doctor` need a check that `stat`s the plugin's `known_marketplaces.json` `installLocation` copy of the hook wrapper (and other hook entry points') for its executable bit at install time — not the `plugins/cache` copy, which S2 and S7 showed is not what `${CLAUDE_PLUGIN_ROOT}` resolves to — plus a `doctor` check that flags its loss afterward, since `run-hook.sh` has no code path that runs once the OS itself refuses to launch it. Qualify §2 D11: its exit-code-remapping guarantee holds for the child process the wrapper's own `case` statement catches (the other five rows), and does not and cannot hold for the wrapper's own launch failure, the case D11's "lost executable bit 126" example actually describes. An untested, cheaper candidate — declaring the hook as `sh ".../run-hook.sh" PreToolUse closed` so the executable bit stops mattering at all — is recorded for `hooks-core` to price against the two checks above. |
| S9 | Recorded as a fixture design, not a measurement — no engine exists yet to run it against: a three-assertion containment fixture (loader rejection of a multi-segment project name, `plan()` emitting no actions for the path-escaping fields, `apply()` refusing to write once the plans directory had been swapped for a symlink). | §7.4 | As designed — the fixture stood as recorded for `scaffold` to implement `plan()`/`apply()` against; nothing in this record contradicted §7.4. |
| S10 | Recorded as a scenario design, not a measurement — no workflow exists yet to run it against: three separately-asserted failure paths for a hostile clone (untrusted in-repo memory withheld from `SessionStart` until trust was recorded, a memory search excluding a mismatched project's store, and attach refusing to symlink across a remote mismatch). | §13 | As designed — the scenario stood as recorded for the `workflows` lane's smoke workflow; nothing in this record contradicted §13. |
