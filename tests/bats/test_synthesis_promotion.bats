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

@test "history with promoted-by multi-persona entry validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "addressed": [
        {
          "file": "src/a.ts",
          "line": 42,
          "summary": "missing null check on user input",
          "promoted_from": "suggestion",
          "promoted_by": "multi-persona",
          "promotion_reason": "multi_source",
          "source_reviewers": ["correctness", "security"]
        }
      ]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "history with promoted-by adversary entry validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "addressed": [
        {
          "file": "src/a.ts",
          "line": 42,
          "summary": "missing null check on user input",
          "promoted_from": "suggestion",
          "promoted_by": "adversary",
          "promotion_reason": "adversary_endorsed",
          "source_reviewers": ["adversary", "correctness"]
        }
      ]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "history with legacy string addressed entry still validates (backward compat)" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "addressed": ["src/a.ts:42 — missing null check"]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "promoted_by with unknown source fails" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "addressed": [
        {
          "file": "src/a.ts",
          "line": 42,
          "summary": "x",
          "promoted_from": "suggestion",
          "promoted_by": "ci"
        }
      ]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"promoted_by"* ]]
}

@test "two-persona suggestion at same file/line matches via matcher script" {
  # the synthesizer prompt uses match_findings.py to decide whether two
  # reviewer findings represent the same concern. this test asserts that the
  # matcher returns 'match' for the kind of pair the prompt would promote.
  echo '{"file":"src/a.ts","line":42,"summary":"missing null check on user input"}' > "${BATS_TEST_TMPDIR}/a.json"
  echo '{"file":"src/a.ts","line":43,"summary":"missing null check when input is empty"}' > "${BATS_TEST_TMPDIR}/b.json"
  run python3 "${SCRIPTS}/match_findings.py" "${BATS_TEST_TMPDIR}/a.json" "${BATS_TEST_TMPDIR}/b.json"
  [[ "$status" -eq 0 ]]
}

@test "single-persona finding at different file does not match across reviewers" {
  echo '{"file":"src/a.ts","line":42,"summary":"missing null check"}' > "${BATS_TEST_TMPDIR}/a.json"
  echo '{"file":"src/b.ts","line":42,"summary":"missing null check"}' > "${BATS_TEST_TMPDIR}/b.json"
  run python3 "${SCRIPTS}/match_findings.py" "${BATS_TEST_TMPDIR}/a.json" "${BATS_TEST_TMPDIR}/b.json"
  [[ "$status" -eq 1 ]]
}

@test "promoted-object entry missing source_reviewers fails" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "addressed": [
        {
          "file": "src/a.ts",
          "line": 42,
          "summary": "missing null check on user input",
          "promoted_from": "suggestion",
          "promoted_by": "multi-persona"
        }
      ]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  # the addressed item fails both oneOf branches (not a string, and missing
  # required source_reviewers on the object form). the jsonschema lib surfaces
  # this as a top-level oneOf failure, so the assertion is on status alone.
}

@test "promoted-object entry with unknown extra property fails" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "addressed": [
        {
          "file": "src/a.ts",
          "line": 42,
          "summary": "x",
          "promoted_from": "suggestion",
          "promoted_by": "multi-persona",
          "source_reviewers": ["correctness", "security"],
          "bogus": true
        }
      ]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"bogus"* || "$output" == *"additionalProperties"* ]]
}

@test "history with deferred promoted-by multi-persona entry validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "deferred": [
        {
          "file": "src/a.ts",
          "line": 42,
          "summary": "consider renaming for clarity",
          "promoted_from": "suggestion",
          "promoted_by": "multi-persona",
          "promotion_reason": "multi_source",
          "source_reviewers": ["readability", "yagni"]
        }
      ]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "history with deferred promoted_by unknown source fails" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "deferred": [
        {
          "file": "src/a.ts",
          "line": 42,
          "summary": "x",
          "promoted_from": "suggestion",
          "promoted_by": "ci"
        }
      ]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"promoted_by"* ]]
}

@test "history with legacy string deferred entry still validates (backward compat)" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "deferred": ["src/a.ts:42 — consider renaming for clarity"]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "addressed entry with promotion_reason=multi_source validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "findings": [], "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
    "addressed": [{
      "file": "src/a.ts", "line": 42,
      "summary": "missing null check",
      "promoted_from": "suggestion",
      "promoted_by": "multi-persona",
      "promotion_reason": "multi_source",
      "source_reviewers": ["correctness", "security"]
    }]
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "addressed entry with promotion_reason=adversary_endorsed validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "findings": [], "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
    "addressed": [{
      "file": "src/a.ts", "line": 42,
      "summary": "missing null check",
      "promoted_from": "suggestion",
      "promoted_by": "adversary",
      "promotion_reason": "adversary_endorsed",
      "source_reviewers": ["adversary", "correctness"]
    }]
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "addressed entry with promotion_reason=evidence_gated_solo_adversary validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "findings": [], "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
    "addressed": [{
      "file": "src/a.ts", "line": 42,
      "summary": "missing null check",
      "promoted_from": "suggestion",
      "promoted_by": "adversary",
      "promotion_reason": "evidence_gated_solo_adversary",
      "source_reviewers": ["adversary"]
    }]
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "deferred entry with promotion_reason=evidence_verification_failed validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "findings": [], "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
    "deferred": [{
      "file": "src/a.ts", "line": 42,
      "summary": "missing null check",
      "promoted_from": "suggestion",
      "promoted_by": "adversary",
      "promotion_reason": "evidence_verification_failed",
      "source_reviewers": ["adversary"]
    }]
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "promoted-object without promotion_reason validates (backward compat for PR #5 state files)" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "findings": [], "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
    "addressed": [{
      "file": "src/a.ts", "line": 42,
      "summary": "s",
      "promoted_from": "suggestion",
      "promoted_by": "multi-persona",
      "source_reviewers": ["correctness"]
    }]
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "promoted-object with unknown promotion_reason fails" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "findings": [], "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
    "addressed": [{
      "file": "src/a.ts", "line": 42, "summary": "s",
      "promoted_from": "suggestion",
      "promoted_by": "multi-persona",
      "promotion_reason": "vibes",
      "source_reviewers": ["correctness"]
    }]
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
}

@test "history.demoted[] with valid entries validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "findings": [], "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
    "demoted": [
      {"file":"src/a.ts","line":10,"summary":"not actually a bug","reviewer":"correctness","reason":"not_a_problem"},
      {"file":"src/b.ts","line":20,"summary":"demoted to suggestion","reviewer":"security","reason":"synthesis_demoted","note":"single weak signal"}
    ]
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "history.demoted absent validates (backward compat)" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "findings": [], "ci_status": "skipped",
    "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []}
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "history.demoted unknown reason fails" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "findings": [], "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
    "demoted": [{"file":"a","line":1,"summary":"s","reviewer":"x","reason":"bogus"}]
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
}

@test "history.findings[] with finding_evidence and move_b_pattern validates" {
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1, "owner": "a", "repo": "b",
  "base_branch": "main", "head_branch": "feat/x",
  "iteration": 1, "max_iterations": 15, "status": "running",
  "history": [{
    "iteration": 0, "head_sha_before": "abc", "head_sha_after": "def",
    "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
    "findings": [{
      "reviewer":"correctness","severity":"blocker","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"s","detail":"d",
      "move_b_pattern":"missing required on schema entry",
      "finding_evidence":{"file":"src/a.ts","line":10,"symbol":"foo"}
    }]
  }]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 0 ]]
}

@test "out_of_scope findings cannot be promoted: schema rejects promoted_from with out_of_scope-only context (sanity)" {
  # the matcher and schema do not encode scope, but the synthesizer prompt does
  # (it only matches in_scope:suggestion entries). this case is a doc anchor:
  # we keep the test thin to assert the schema doesn't accidentally invent a
  # promoted_from enum value beyond 'suggestion'.
  cat > "${BATS_TEST_TMPDIR}/state.json" <<'JSON'
{
  "pr_url": "https://github.com/a/b/pull/1",
  "pr_number": 1,
  "owner": "a",
  "repo": "b",
  "base_branch": "main",
  "head_branch": "feat/x",
  "iteration": 1,
  "max_iterations": 15,
  "status": "running",
  "history": [
    {
      "iteration": 0,
      "head_sha_before": "abc",
      "head_sha_after": "def",
      "findings": [],
      "ci_status": "skipped",
      "panel_selection": {"mode": "full", "ran": [], "skipped": [], "gate_relevant": [], "gate_fail_open": [], "open_blocker_carryover": []},
      "addressed": [
        {
          "file": "src/a.ts",
          "line": 1,
          "summary": "x",
          "promoted_from": "out_of_scope"
        }
      ]
    }
  ]
}
JSON
  run validate_state "${BATS_TEST_TMPDIR}/state.json"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"promoted_from"* ]]
}
