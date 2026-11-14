#!/usr/bin/env bats

load test_helper

flag() {
  echo "$1" | python3 "${SCRIPTS}/flag_shallow_reviews.py"
}

@test "approve with files_read populated is not shallow" {
  local out
  out=$(flag '[{"reviewer":"correctness","verdict":"approve","findings":[],"evidence":{"files_read":["a.ts"]}}]')
  [[ "$(jq -r '.shallow_review | length' <<<"$out")" == "0" ]]
}

@test "approve with no evidence key is shallow" {
  local out
  out=$(flag '[{"reviewer":"correctness","verdict":"approve","findings":[]}]')
  [[ "$(jq -r '.shallow_review[0]' <<<"$out")" == "correctness" ]]
}

@test "approve with empty evidence object is shallow" {
  local out
  out=$(flag '[{"reviewer":"security","verdict":"approve","findings":[],"evidence":{}}]')
  [[ "$(jq -r '.shallow_review[0]' <<<"$out")" == "security" ]]
}

@test "approve with empty files_read array is shallow" {
  local out
  out=$(flag '[{"reviewer":"tests","verdict":"approve","findings":[],"evidence":{"files_read":[]}}]')
  [[ "$(jq -r '.shallow_review[0]' <<<"$out")" == "tests" ]]
}

@test "request_changes with empty evidence is not shallow" {
  local out
  out=$(flag '[{"reviewer":"performance","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","summary":"s","file":"a","line":1,"detail":"d"}]}]')
  [[ "$(jq -r '.shallow_review | length' <<<"$out")" == "0" ]]
}

@test "comment verdict with empty evidence is not shallow" {
  local out
  out=$(flag '[{"reviewer":"readability","verdict":"comment","findings":[]}]')
  [[ "$(jq -r '.shallow_review | length' <<<"$out")" == "0" ]]
}

@test "output is alphabetical and includes only shallow reviewers" {
  local out
  out=$(flag '[
    {"reviewer":"correctness","verdict":"approve","findings":[],"evidence":{"files_read":["a.ts"]}},
    {"reviewer":"security","verdict":"approve","findings":[]},
    {"reviewer":"tests","verdict":"approve","findings":[],"evidence":{}},
    {"reviewer":"performance","verdict":"approve","findings":[],"evidence":{"files_read":[]}}
  ]')
  [[ "$(jq -c .shallow_review <<<"$out")" == '["performance","security","tests"]' ]]
}

@test "non-array stdin exits 2" {
  run bash -c 'echo "{}" | python3 "'${SCRIPTS}'/flag_shallow_reviews.py"'
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"JSON array"* ]]
}

@test "invalid JSON stdin exits 2" {
  run bash -c 'echo "{" | python3 "'${SCRIPTS}'/flag_shallow_reviews.py"'
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"not valid JSON"* ]]
}

@test "approve with evidence as non-dict (list) is shallow" {
  local out
  out=$(flag '[{"reviewer":"correctness","verdict":"approve","findings":[],"evidence":["a.ts"]}]')
  [[ "$(jq -r '.shallow_review[0]' <<<"$out")" == "correctness" ]]
}

@test "approve with files_read as non-list (string) is shallow" {
  local out
  out=$(flag '[{"reviewer":"security","verdict":"approve","findings":[],"evidence":{"files_read":"a.ts"}}]')
  [[ "$(jq -r '.shallow_review[0]' <<<"$out")" == "security" ]]
}

@test "adversary approve with no evidence is shallow" {
  local out
  out=$(flag '[{"reviewer":"adversary","verdict":"approve","findings":[]}]')
  [[ "$(jq -r '.shallow_review[0]' <<<"$out")" == "adversary" ]]
}

@test "adversary approve with populated evidence is not shallow" {
  local out
  out=$(flag '[{"reviewer":"adversary","verdict":"approve","findings":[],"evidence":{"files_read":["a.ts"]}}]')
  [[ "$(jq -r '.shallow_review | length' <<<"$out")" == "0" ]]
}

@test "adversary alongside panel personas is flagged independently" {
  local out
  out=$(flag '[
    {"reviewer":"correctness","verdict":"approve","findings":[],"evidence":{"files_read":["a.ts"]}},
    {"reviewer":"adversary","verdict":"approve","findings":[]}
  ]')
  [[ "$(jq -c .shallow_review <<<"$out")" == '["adversary"]' ]]
}

@test "adversary request_changes with empty evidence is not shallow" {
  local out
  out=$(flag '[{"reviewer":"adversary","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","summary":"s","file":"a","line":1,"detail":"d"}]}]')
  [[ "$(jq -r '.shallow_review | length' <<<"$out")" == "0" ]]
}
