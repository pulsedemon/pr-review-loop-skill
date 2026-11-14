#!/usr/bin/env bats

# Pins the history-entry schema surfaces added by the shallow-adversary and
# delta-gate work. Cap-maximum assertions (numeric values on
# shallow_adversary_runs / shallow_approval_adversary_runs) are owned by
# scripts/regen_adversary_caps.py (mirror writer; manifests/adversary-caps.yaml
# is the source of truth) and tests/bats/test_adversary_cap_behavioral.bats
# (behavioral / sourceability / dual-counter canaries).

load test_helper

@test "state schema allows adversary.shallow_blocker boolean on history entries" {
  run jq -e '.properties.history.items.properties.adversary.properties.shallow_blocker' "${REPO_ROOT}/templates/state.schema.json"
  [ "$status" -eq 0 ]
  run jq -re '.properties.history.items.properties.adversary.properties.shallow_blocker.type' "${REPO_ROOT}/templates/state.schema.json"
  [ "$output" = "boolean" ]
}

@test "state schema allows adversary_shallow_giveup boolean on history entries" {
  run jq -e '.properties.history.items.properties.adversary_shallow_giveup' "${REPO_ROOT}/templates/state.schema.json"
  [ "$status" -eq 0 ]
  run jq -re '.properties.history.items.properties.adversary_shallow_giveup.type' "${REPO_ROOT}/templates/state.schema.json"
  [ "$output" = "boolean" ]
}

@test "history item allows panel_selection with the documented sub-fields" {
  local schema props
  schema="${REPO_ROOT}/templates/state.schema.json"
  run jq -e '.properties.history.items.properties.panel_selection' "$schema"
  [ "$status" -eq 0 ]
  props=$(jq -r '.properties.history.items.properties.panel_selection.properties | keys | sort | join(",")' "$schema")
  [ "$props" = "gate_fail_open,gate_relevant,mode,open_blocker_carryover,ran,skipped" ]
}

@test "history item requires panel_selection" {
  local schema
  schema="${REPO_ROOT}/templates/state.schema.json"
  run jq -er '.properties.history.items.required | index("panel_selection")' "$schema"
  [ "$status" -eq 0 ]
}

@test "history item allows forced_full_sweep boolean" {
  local schema t
  schema="${REPO_ROOT}/templates/state.schema.json"
  t=$(jq -r '.properties.history.items.properties.forced_full_sweep.type' "$schema")
  [ "$t" = "boolean" ]
}

@test "history item allows model_routing for the fan-out phases" {
  local schema props
  schema="${REPO_ROOT}/templates/state.schema.json"
  run jq -e '.properties.history.items.properties.model_routing' "$schema"
  [ "$status" -eq 0 ]
  props=$(jq -r '.properties.history.items.properties.model_routing.properties | keys | sort | join(",")' "$schema")
  [ "$props" = "adversary,delta_gate,reviewer" ]
  run jq -re '.properties.history.items.properties.model_routing.additionalProperties' "$schema"
  [ "$output" = "false" ]
}

@test "model_routing phases reference the shared phase_model defs" {
  local schema ref
  schema="${REPO_ROOT}/templates/state.schema.json"
  for phase in delta_gate reviewer adversary; do
    ref=$(jq -r ".properties.history.items.properties.model_routing.properties.${phase}.\"\$ref\"" "$schema")
    [ "$ref" = "#/\$defs/phase_model" ]
  done
  local tiers
  tiers=$(jq -rc '.["$defs"].phase_model.properties.tier.enum' "$schema")
  [ "$tiers" = '["inherit","cheap","standard","strong"]' ]
}

@test "state schema allows a top-level comment_ledger array" {
  local schema t
  schema="${REPO_ROOT}/templates/state.schema.json"
  run jq -e '.properties.comment_ledger' "$schema"
  [ "$status" -eq 0 ]
  t=$(jq -r '.properties.comment_ledger.type' "$schema")
  [ "$t" = "array" ]
}

@test "comment_ledger items require id/source/disposition/replied_at" {
  local schema req
  schema="${REPO_ROOT}/templates/state.schema.json"
  req=$(jq -r '.properties.comment_ledger.items.required | sort | join(",")' "$schema")
  [ "$req" = "disposition,id,replied_at,source" ]
  run jq -re '.properties.comment_ledger.items.additionalProperties' "$schema"
  [ "$output" = "false" ]
  local disp
  disp=$(jq -rc '.properties.comment_ledger.items.properties.disposition.enum' "$schema")
  [ "$disp" = '["addressed","deferred"]' ]
}

@test "history item requires ci_failed_checks when ci_status is failure (if/then)" {
  local schema
  schema="${REPO_ROOT}/templates/state.schema.json"
  run jq -re '.properties.history.items.if.properties.ci_status.const' "$schema"
  [ "$output" = "failure" ]
  run jq -re '.properties.history.items.then.required | index("ci_failed_checks")' "$schema"
  [ "$status" -eq 0 ]
  run jq -re '.properties.history.items.then.properties.ci_failed_checks.minItems' "$schema"
  [ "$output" = "1" ]
}

@test "comment_ledger requires reason when disposition is deferred (if/then)" {
  local schema
  schema="${REPO_ROOT}/templates/state.schema.json"
  run jq -re '.properties.comment_ledger.items.if.properties.disposition.const' "$schema"
  [ "$output" = "deferred" ]
  run jq -re '.properties.comment_ledger.items.then.required | index("reason")' "$schema"
  [ "$status" -eq 0 ]
}
