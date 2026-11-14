#!/usr/bin/env bats

# Regression test for SKILL.md §1 terminal-status contract:
# every documented exit status must validate as a `status` value in
# templates/state.schema.json. Pins the schema to the SETUP_ERROR
# contract so a future rename in SKILL.md cannot silently drift away
# from the schema enum.

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

write_state_with_status() {
  local status="$1"
  cat > "${BATS_TEST_TMPDIR}/state.json" <<JSON
{
  "pr_url": "https://github.com/acme/api/pull/1",
  "pr_number": 1,
  "owner": "acme",
  "repo": "api",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 0,
  "max_iterations": 15,
  "status": "${status}",
  "history": []
}
JSON
}

setup() {
  cd "${REPO_ROOT}"
}

@test "running status validates" {
  write_state_with_status "running"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "success status validates" {
  write_state_with_status "success"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "max_iterations status validates" {
  write_state_with_status "max_iterations"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "no_progress status validates" {
  write_state_with_status "no_progress"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "tests_regressed status validates" {
  write_state_with_status "tests_regressed"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "ci_stuck status validates" {
  write_state_with_status "ci_stuck"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "external_push status validates" {
  write_state_with_status "external_push"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "scope_split_recommended status validates" {
  write_state_with_status "scope_split_recommended"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "setup_error status validates (the SKILL.md SETUP_ERROR contract)" {
  write_state_with_status "setup_error"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "the previously-buggy 'aborted' status is rejected" {
  write_state_with_status "aborted"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -ne 0 ]]
}

@test "unknown status is rejected" {
  write_state_with_status "definitely_not_a_status"
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -ne 0 ]]
}
