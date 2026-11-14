#!/usr/bin/env bats

load test_helper

@test "reviewer output with populated evidence passes" {
  local payload='{"reviewer":"correctness","verdict":"approve","findings":[],"evidence":{"files_read":["src/a.ts","src/b.ts"],"symbols_traced":["doThing"],"notes":"checked callers in src/c.ts"}}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "reviewer output without evidence still passes (backward compat)" {
  local payload='{"reviewer":"correctness","verdict":"approve","findings":[]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "evidence with unknown property fails" {
  local payload='{"reviewer":"correctness","verdict":"approve","findings":[],"evidence":{"files_read":[],"bogus":true}}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"bogus"* || "$output" == *"additionalProperties"* ]]
}

@test "evidence with wrong type for files_read fails" {
  local payload='{"reviewer":"correctness","verdict":"approve","findings":[],"evidence":{"files_read":"src/a.ts"}}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"files_read"* || "$output" == *"array"* ]]
}

@test "evidence with empty object passes" {
  local payload='{"reviewer":"correctness","verdict":"approve","findings":[],"evidence":{}}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "evidence with wrong type for symbols_traced fails" {
  local payload='{"reviewer":"correctness","verdict":"approve","findings":[],"evidence":{"symbols_traced":"doThing"}}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"symbols_traced"* || "$output" == *"array"* ]]
}

@test "evidence with wrong type for notes fails" {
  local payload='{"reviewer":"correctness","verdict":"approve","findings":[],"evidence":{"notes":42}}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"notes"* || "$output" == *"string"* ]]
}
