#!/usr/bin/env bats
# tests/bats/test_metrics_cross_record_invariant.bats — assert the §4i
# per-iteration counters and the Step 5 terminal totals stay in lockstep.
#
# This is the bats promotion of scenario 21's recipe so a future change
# that adds a promotion_reason and updates only one of the two writers
# trips CI instead of waiting for a manual end-to-end run.

load test_helper

setup() {
  TMP="$(mktemp -d)"
  METRICS="$TMP/metrics.jsonl"
  cat > "$METRICS" <<'JSONL'
{"kind":"iteration","iteration":1,"promoted":{"multi_source":2,"adversary_endorsed":1,"evidence_gated_solo_adversary":0},"failed":{"evidence_verification":1}}
{"kind":"iteration","iteration":2,"promoted":{"multi_source":1,"adversary_endorsed":0,"evidence_gated_solo_adversary":3},"failed":{"evidence_verification":2}}
{"kind":"terminal","totals":{"promoted_multi_source":3,"promoted_adversary_endorsed":1,"promoted_evidence_gated_solo_adversary":3,"evidence_verification_failed":3}}
JSONL
}

teardown() {
  rm -rf "$TMP"
}

assert_pair() {
  local terminal_key="$1" iter_path="$2"
  local term iter_sum
  term=$(grep '"kind":"terminal"' "$METRICS" | tail -1 | jq ".totals.${terminal_key}")
  iter_sum=$(grep '"kind":"iteration"' "$METRICS" | jq -s "[.[].${iter_path}] | add")
  [ "$term" = "$iter_sum" ] || {
    echo "mismatch: totals.${terminal_key}=${term} vs sum(${iter_path})=${iter_sum}" >&2
    return 1
  }
}

@test "totals.promoted_multi_source == sum(promoted.multi_source)" {
  assert_pair promoted_multi_source promoted.multi_source
}

@test "totals.promoted_adversary_endorsed == sum(promoted.adversary_endorsed)" {
  assert_pair promoted_adversary_endorsed promoted.adversary_endorsed
}

@test "totals.promoted_evidence_gated_solo_adversary == sum(promoted.evidence_gated_solo_adversary)" {
  assert_pair promoted_evidence_gated_solo_adversary promoted.evidence_gated_solo_adversary
}

@test "totals.evidence_verification_failed == sum(failed.evidence_verification)" {
  assert_pair evidence_verification_failed failed.evidence_verification
}

@test "divergent terminal totals are caught" {
  # corrupt the terminal record so totals do not match per-iteration sums.
  cat > "$METRICS" <<'JSONL'
{"kind":"iteration","iteration":1,"promoted":{"multi_source":2}}
{"kind":"iteration","iteration":2,"promoted":{"multi_source":1}}
{"kind":"terminal","totals":{"promoted_multi_source":99}}
JSONL
  run assert_pair promoted_multi_source promoted.multi_source
  [ "$status" -ne 0 ]
}
