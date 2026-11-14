#!/usr/bin/env bats
# tests/bats/test_metric_jq_guards.bats — behavioral check on the §4i and
# Step 5 metric jq selects. State schema allows legacy-string entries in
# history[].addressed[] / history[].deferred[] for PR #5 backward compat
# (see test_synthesis_promotion.bats); without the type==object guard the
# select pipeline crashes with "Cannot index string with string" and the
# metric record is silently dropped.

load test_helper

setup() {
  TMP="$(mktemp -d)"
}

teardown() {
  rm -rf "$TMP"
}

# Mixed history with one legacy-string addressed entry and one object entry
# carrying promotion_reason=multi_source. Mirrors the shape callers in SKILL.md
# §4i (single $hist) and Step 5 ($st.history[].addressed[]?) operate on.
write_mixed_history() {
  cat > "$TMP/state.json" <<'JSON'
{
  "history": [
    {
      "iteration": 0,
      "addressed": [
        "legacy-string-from-pr5",
        {"reviewer": "correctness", "promotion_reason": "multi_source"},
        {"reviewer": "tests"}
      ],
      "deferred": [
        "legacy-deferred-string",
        {"reviewer": "security", "promotion_reason": "evidence_verification_failed"}
      ]
    }
  ]
}
JSON
}

@test "§4i per-iteration select skips legacy-string addressed entries" {
  write_mixed_history
  run jq '[.history[0].addressed[]? | select(type=="object" and .promotion_reason=="multi_source")] | length' "$TMP/state.json"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "§4i per-iteration select skips legacy-string deferred entries" {
  write_mixed_history
  run jq '[.history[0].deferred[]? | select(type=="object" and .promotion_reason=="evidence_verification_failed")] | length' "$TMP/state.json"
  [ "$status" -eq 0 ]
  [ "$output" = "1" ]
}

@test "Step 5 terminal select aggregates objects across history and skips strings" {
  cat > "$TMP/state.json" <<'JSON'
{
  "history": [
    {"addressed": ["legacy", {"promotion_reason": "multi_source"}]},
    {"addressed": [{"promotion_reason": "adversary_endorsed"}]},
    {"addressed": [{"promotion_reason": "multi_source"}, "legacy"]}
  ]
}
JSON
  run jq '[.history[].addressed[]? | select(type=="object" and .promotion_reason=="multi_source")] | length' "$TMP/state.json"
  [ "$status" -eq 0 ]
  [ "$output" = "2" ]
}

@test "without the type==object guard the same pipeline crashes on legacy strings" {
  write_mixed_history
  run jq '[.history[0].addressed[]? | select(.promotion_reason=="multi_source")] | length' "$TMP/state.json"
  [ "$status" -ne 0 ]
}

@test "SKILL.md §4i and Step 5 promotion_reason selects all carry the type==object guard" {
  unguarded=$(grep -nE 'select\(\.promotion_reason==' \
    "${REPO_ROOT}/SKILL.md" \
    "${REPO_ROOT}/scripts/write_iteration_metric.sh" \
    "${REPO_ROOT}/scripts/write_terminal_metric.sh" \
    || true)
  [ -z "$unguarded" ] || {
    echo "unguarded promotion_reason selects (no type==object guard) in:" >&2
    echo "$unguarded" >&2
    return 1
  }
}
