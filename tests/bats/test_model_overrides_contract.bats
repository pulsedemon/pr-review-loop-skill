#!/usr/bin/env bats

# Model override cross-surface drift guard. Pins the portable contract:
#   1. SKILL.md exposes the user inputs and points to canonical mechanics;
#   2. docs/model-overrides.md owns phase keys, precedence, fallback and the
#      Codex tier-to-family mapping;
#   3. AGENTS.md includes the Codex spawn_agent.model note;
#   4. README.md shows the cost_saver and inherit invocations;
#   5. the Witch section of docs/model-overrides.md owns routing, effort,
#      lean launches and several-route dispatch under Witch.

load test_helper

assert_patterns() {
  local path="$1"
  shift

  run python3 - <<'PY' "$path" "$@"
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
args = sys.argv[2:]

if len(args) % 2:
    raise SystemExit("expected pattern/message pairs")

text = path.read_text()
for pattern, message in zip(args[::2], args[1::2]):
    if not re.search(pattern, text, re.IGNORECASE | re.DOTALL):
        raise SystemExit(message)
PY
  [ "$status" -eq 0 ]
}

@test "SKILL.md documents model override inputs and mechanics doc" {
  assert_patterns "${REPO_ROOT}/SKILL.md" \
    'subagent_model_profile.*default [`"]?balanced[`"]?.*inherit.*cost_saver' \
    "missing subagent_model_profile input contract" \
    "subagent_model_overrides.*delta_gate.*reviewer.*adversary.*pr_scope.*inherit.*cheap.*standard.*strong" \
    "missing subagent_model_overrides input contract" \
    "docs/model-overrides\\.md" \
    "missing model-overrides mechanics link"
}

@test "docs/model-overrides.md defines phase keys, precedence, and fallback" {
  assert_patterns "${REPO_ROOT}/docs/model-overrides.md" \
    "delta_gate.*reviewer.*adversary.*pr_scope" \
    "missing required phase keys" \
    "Explicit.*subagent_model_overrides\\.<phase>.*wins" \
    "missing explicit override precedence" \
    "balanced.*delta_gate.*pr_scope.*cheap.*reviewer.*standard.*adversary.*strong" \
    "missing balanced default phase mapping" \
    "cost_saver.*delta_gate.*pr_scope.*reviewer.*cheap.*adversary.*standard" \
    "missing cost_saver phase mapping" \
    "unsupported.*fall back to (the )?inherited model.*continue" \
    "missing fallback-to-inherit rule" \
    "unknown.*subagent_model_profile.*inherit" \
    "missing unknown profile fallback rule" \
    "unknown.*phase.*ignored" \
    "missing unknown phase ignore rule" \
    "unknown.*tier.*inherit" \
    "missing unknown tier fallback rule" \
    "must never block the loop" \
    "missing malformed-input non-blocking rule"
}

@test "docs/model-overrides.md defines local-only observability and recording" {
  assert_patterns "${REPO_ROOT}/docs/model-overrides.md" \
    "Observability and recording" \
    "missing observability section" \
    "never in the posted PR comment" \
    "missing posted-comment exclusion rule" \
    "history\\[N\\]\\.model_routing" \
    "missing history model_routing recording rule" \
    "best-effort.*skip the field and continue" \
    "missing best-effort recording fallback"
}

@test "docs/model-overrides.md defines Codex unavailable-model fallback" {
  assert_patterns "${REPO_ROOT}/docs/model-overrides.md" \
    'Codex.*unavailable.*same portable tier.*otherwise.*fall back to [`"]?inherit[`"]?.*omit.*spawn_agent\.model.*continue' \
    "missing Codex same-tier then inherit fallback rule"
}

@test "docs/model-overrides.md maps Codex tiers to model families" {
  assert_patterns "${REPO_ROOT}/docs/model-overrides.md" \
    '### Codex.*\| `cheap` \| `luna` \|.*\| `standard` \| `sol` \|.*\| `strong` \| `astra` \|.*### opencode' \
    "missing Codex tier to family mapping"
}

@test "docs/model-overrides.md defines opencode tier-agent mapping and fallbacks" {
  assert_patterns "${REPO_ROOT}/docs/model-overrides.md" \
    '### opencode.*subagent_type.*prl-cheap.*prl-standard.*prl-strong.*general' \
    "missing opencode tier to subagent_type mapping" \
    'opencode.*no per-invocation model' \
    "missing opencode no-per-invocation-model constraint" \
    'not registered.*fall back to [`"]?general[`"]?.*continue' \
    "missing opencode unregistered-agent fallback rule" \
    'honors true [`"]?inherit[`"]?' \
    "missing opencode true-inherit statement" \
    'model-less agent inherits.*orchestration session.*model|task.*falls back to the parent message' \
    "missing opencode parent-model fallback mechanic"
}

@test "AGENTS.md includes Codex spawn_agent.model routing note" {
  assert_patterns "${REPO_ROOT}/AGENTS.md" \
    'non-inherited.*tiers map to [`"]?spawn_agent\.model[`"]?' \
    "missing Codex spawn_agent.model mapping note" \
    'model-overrides\.md#witch' \
    "missing pointer to the Witch section"
}

# Print the `### Witch` section of docs/model-overrides.md; fail when it is missing.
_witch_section() {
  awk '
    $0 == "### Witch" { found = 1; next }
    found && /^##/ { exit }
    found { print }
    END { exit !found }
  ' "${REPO_ROOT}/docs/model-overrides.md" || {
    echo "docs/model-overrides.md has no '### Witch' section" >&2
    return 1
  }
}

# Each pin occurs once in the section, so deleting its sentence fails the test.
_pin() {
  local body="$1" phrase
  shift
  for phrase in "$@"; do
    grep -qiF -- "$phrase" <<<"$body" || {
      echo "Witch section missing: $phrase"
      return 1
    }
  done
}

@test "Witch section routes each phase by work kind" {
  local body
  body=$(_witch_section) || return 1
  _pin "$body" \
    "every phase delegates through Witch's familiar wrappers after \`--route\`" \
    "replaces the Claude Code and Codex sections' spawn and tier mappings" \
    '| `delta_gate` | `investigation` |' \
    '| `reviewer` | `review` |' \
    '| `adversary` | `investigation` |' \
    '| `pr_scope` | `investigation` |' \
    "starts on the parent's runtime unless Witch's capacity balancing moves it" \
    'A panel route passes `--of <producer runtime>:<producer model>`' \
    'A tiered phase routes with `--tier <tier>`' \
    'replaces the inherit fallback above'
}

@test "Witch section keeps inherit and refusals single-route" {
  local body
  body=$(_witch_section) || return 1
  _pin "$body" \
    'An `inherit` phase routes with `--named <parent runtime>:<parent model>`' \
    'never routed twice for coverage' \
    'A refused route goes to the user' \
    'is not retried without the tier' \
    'for `inherit` the echo says the tier was not honoured'
}

@test "Witch section maps tiers to effort on both runtimes" {
  local body
  body=$(_witch_section) || return 1
  _pin "$body" \
    'passed as `-c model_reasoning_effort="<level>"` on Codex and `--effort <level>` on Claude' \
    '| Tier | Codex | Claude |' \
    '| `cheap` | `low` | `low` |' \
    '| `standard` | `medium` | `medium` |' \
    '| `strong` | `high` | `high` |' \
    '`inherit` passes no effort flag'
}

@test "Witch section launches familiars lean" {
  local body
  body=$(_witch_section) || return 1
  _pin "$body" \
    "Codex with Witch's \`--without-mcp\`" \
    'Claude with `--strict-mcp-config` and `--disable-slash-commands`' \
    'pulsedemon/witch#919'
}

@test "Witch section dispatches and records every route" {
  local body
  body=$(_witch_section) || return 1
  _pin "$body" \
    'launch `max(N, R)` familiars' \
    'familiar `k` runs persona `k mod N` on route `k mod R`' \
    '`folded` placements already run on an existing route and get no familiar' \
    'A batch with no selected persona is not routed' \
    "The panel's [reviewer budget](reviewer-orchestration.md#reviewer-budget) applies per familiar" \
    '[`scripts/familiar_response.py`](../scripts/familiar_response.py)' \
    'A fenced object is malformed' \
    'relaunched once per phase per iteration' \
    'keep only returned routes on another runtime' \
    'record `model_routing.<phase>.model` as the route models joined by `, ` in route order'
}

@test "Witch section reduces several results per persona" {
  local body
  body=$(_witch_section) || return 1
  _pin "$body" \
    'every valid panel output goes to synthesis under its persona name' \
    'the persona gets one receipt if any output validates' \
    'records its own `reviewer_errors` entry, even beside another route'"'"'s valid output' \
    'a persona with any failed or invalid gate familiar gets no gate result' \
    '`relevant: true` if any familiar says so' \
    'a missing or invalid response records `adversary_error` naming each failure' \
    'into `history[].findings`' \
    'persist the first valid `request_split` in route order' \
    'Scope errors are recorded beside a valid recommendation' \
    'takes the failed-agent row of [`pr-scope.md`](pr-scope.md#substeps)' \
    'route with the phase'"'"'s work kind and `--named <that runtime>:<that model>`' \
    'a valid relaunch recovers the assignment and records no error'
}

@test "state schema documents multi-route model recording" {
  run jq -r '."$defs".phase_model.properties.model.description' \
    "${REPO_ROOT}/templates/state.schema.json"
  [ "$status" -eq 0 ]
  grep -qF 'joined by `, ` in route order' <<<"$output"
}

@test "README.md shows cost_saver and inherit model profile invocations" {
  assert_patterns "${REPO_ROOT}/README.md" \
    "subagent_model_profile=cost_saver" \
    "missing cost_saver usage example" \
    "subagent_model_profile=inherit" \
    "missing inherit usage example"
}
