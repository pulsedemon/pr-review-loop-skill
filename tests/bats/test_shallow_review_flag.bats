#!/usr/bin/env bats

load test_helper

# Minimal valid state.json with one history entry that records a shallow_review
# flag. Validates against templates/state.schema.json.
write_state_with_shallow_review() {
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
  "shallow_adversary_runs": 0,
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "deadbeef",
      "head_sha_after": "deadbeef",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "shallow_review": ["correctness", "yagni"]
    }
  ]
}
JSON
}

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

@test "history entry with shallow_review array validates" {
  write_state_with_shallow_review
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "history entry with shallow_review wrong type fails validation" {
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
      "shallow_review": "correctness"
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"shallow_review"* ]]
}

@test "history entry without shallow_review (backward compat) validates" {
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
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []}
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "top-level shallow_adversary_runs integer validates" {
  write_state_with_shallow_review
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "top-level shallow_adversary_runs negative fails" {
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
  "shallow_adversary_runs": -1,
  "history": []
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"shallow_adversary_runs"* || "$output" == *"minimum"* ]]
}
