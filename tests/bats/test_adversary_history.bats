#!/usr/bin/env bats

load test_helper

validate_state() {
  python3 - "$1" <<'PY'
import json, sys
from jsonschema import Draft202012Validator
schema = json.load(open("templates/state.schema.json"))
data = json.load(open(sys.argv[1]))
errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.absolute_path))
if errors:
    for e in errors:
        loc = "/".join(str(p) for p in e.absolute_path) or "<root>"
        print(f"{loc}: {e.message}", file=sys.stderr)
    sys.exit(1)
PY
}

setup() {
  cd "${REPO_ROOT}"
}

write_state_with_adversary() {
  local body="$1"
  cat > "${BATS_TEST_TMPDIR}/state.json" <<JSON
{
  "pr_url": "https://github.com/acme/api/pull/1",
  "pr_number": 1,
  "owner": "acme",
  "repo": "api",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "deadbeef",
      "head_sha_after": "deadbeef",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "adversary": ${body}
    }
  ]
}
JSON
}

@test "history entry with fully-populated adversary record validates" {
  write_state_with_adversary '{"reviewer":"adversary","verdict":"approve","findings":[],"evidence":{"files_read":["src/a.ts"],"symbols_traced":["doThing"],"notes":"checked"}}'
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "history adversary record with minimal fields validates" {
  write_state_with_adversary '{"verdict":"approve","findings":[]}'
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "history adversary record with unknown property fails (additionalProperties: false)" {
  write_state_with_adversary '{"verdict":"approve","findings":[],"bogus":1}'
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"bogus"* || "$output" == *"additionalProperties"* ]]
}

@test "history adversary record with bad verdict enum fails" {
  write_state_with_adversary '{"verdict":"meh","findings":[]}'
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"verdict"* || "$output" == *"enum"* ]]
}

@test "history adversary record with reviewer field set to a non-adversary value fails" {
  write_state_with_adversary '{"reviewer":"correctness","verdict":"approve","findings":[]}'
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"reviewer"* || "$output" == *"const"* || "$output" == *"adversary"* ]]
}

@test "history entry with adversary_error string validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/acme/api/pull/1",
  "pr_number": 1,
  "owner": "acme",
  "repo": "api",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "deadbeef",
      "head_sha_after": "deadbeef",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "adversary_error": "validation failed: missing reviewer field"
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "history adversary record with empty object fails (required verdict + findings)" {
  write_state_with_adversary '{}'
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"verdict"* || "$output" == *"findings"* || "$output" == *"required"* ]]
}

@test "history adversary record missing findings fails" {
  write_state_with_adversary '{"verdict":"approve"}'
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"findings"* || "$output" == *"required"* ]]
}

@test "history entry with both adversary and adversary_error fails (mutual exclusion)" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/acme/api/pull/1",
  "pr_number": 1,
  "owner": "acme",
  "repo": "api",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "deadbeef",
      "head_sha_after": "deadbeef",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "adversary": {"verdict": "approve", "findings": []},
      "adversary_error": "validation failed"
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
}

@test "history entry with adversary_error non-string fails" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/acme/api/pull/1",
  "pr_number": 1,
  "owner": "acme",
  "repo": "api",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "deadbeef",
      "head_sha_after": "deadbeef",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "adversary_error": 123
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"adversary_error"* || "$output" == *"string"* ]]
}
