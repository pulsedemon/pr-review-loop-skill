#!/usr/bin/env bats

# Model override cross-surface drift guard. Pins the portable contract:
#   1. SKILL.md exposes the user inputs and points to canonical mechanics;
#   2. docs/model-overrides.md owns phase keys, precedence, fallback and the
#      Codex tier-to-family mapping;
#   3. AGENTS.md includes the Codex spawn_agent.model note;
#   4. README.md shows the cost_saver and inherit invocations.

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
    "missing Codex spawn_agent.model mapping note"
}

@test "README.md shows cost_saver and inherit model profile invocations" {
  assert_patterns "${REPO_ROOT}/README.md" \
    "subagent_model_profile=cost_saver" \
    "missing cost_saver usage example" \
    "subagent_model_profile=inherit" \
    "missing inherit usage example"
}
