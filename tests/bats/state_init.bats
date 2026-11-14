#!/usr/bin/env bats

load test_helper

setup() {
  # Resolve the real `jq` path BEFORE any stub prepends $BATS_TEST_TMPDIR/stubs
  # to PATH. The jq-mismatch test below stubs `jq` itself; without a captured
  # absolute path, the stub's pass-through fallback would recurse into the stub.
  REAL_JQ=$(command -v jq)
  export REAL_JQ
  make_tmp_repo
  stub_cmd gh 'cat <<JSON
{"number":42,"title":"Test","url":"https://github.com/o/r/pull/42","headRefName":"feature","baseRefName":"main","headRefOid":"deadbeef","body":"","isDraft":false}
JSON'
}

@test "fresh init writes state.json" {
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"Initialized"* ]]
  test -f .git/pr-loop/state.json
  jq -e '.pr_number == 42 and .head_branch == "feature"' .git/pr-loop/state.json
}

@test "fresh init persists pr_author from gh metadata" {
  stub_cmd gh 'cat <<JSON
{"number":42,"title":"Test","url":"https://github.com/o/r/pull/42","headRefName":"feature","baseRefName":"main","headRefOid":"deadbeef","body":"","isDraft":false,"author":{"login":"alice"}}
JSON'
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  jq -e '.pr_author == "alice"' .git/pr-loop/state.json
}

@test "gh metadata missing a required key exits 2" {
  # gh omits headRefOid; the init-state helper must fail the documented way
  # (clean exit 2) rather than crashing with an uncaught traceback / exit 1.
  stub_cmd gh 'cat <<JSON
{"number":42,"title":"Test","url":"https://github.com/o/r/pull/42","headRefName":"feature","baseRefName":"main","body":"","isDraft":false,"author":{"login":"alice"}}
JSON'
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"meta JSON missing required key(s)"* ]]
  [[ "$output" == *"headRefOid"* ]]
  [[ ! -e .git/pr-loop/state.json ]]
}

@test "resume same PR is idempotent" {
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"already exists"* ]]
}

@test "resume same PR exits 0 even when gh pr view fails" {
  # Pins the reorder: the existing-state short-circuit runs BEFORE any gh pr
  # view call, so a transient gh/auth failure on resume cannot mask valid
  # resumable state by exiting 7.
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  stub_cmd gh 'echo "gh: could not connect to github.com" >&2; exit 1'
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"already exists"* ]]
}

@test "a completed loop's state for the same PR is reinitialized, not resumed" {
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  local state=".git/pr-loop/state.json"
  jq '.status = "success" | .iteration = 3 | .completed_at = "2026-09-10T17:00:00Z"' "$state" > "$state.tmp" && mv "$state.tmp" "$state"
  echo '{}' > .git/pr-loop/pr-scope.json
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"completed"* ]]
  [[ "$output" != *"already exists"* ]]
  [[ "$(jq -r .status "$state")" == "running" ]]
  [[ "$(jq -r .iteration "$state")" == "0" ]]
  [[ "$(jq -r '.completed_at // empty' "$state")" == "" ]]
  [[ ! -f .git/pr-loop/pr-scope.json ]]
}

@test "a terminal status without the Step 5 marker still resumes" {
  # pr_scope_step.py persists scope_split_recommended before Step 5 runs; a
  # crash there must resume so the split summary still gets posted.
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  local state=".git/pr-loop/state.json"
  jq '.status = "scope_split_recommended"' "$state" > "$state.tmp" && mv "$state.tmp" "$state"
  echo '{"verdict":"request_split"}' > .git/pr-loop/pr-scope.json
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"already exists"* ]]
  [[ "$(jq -r .status "$state")" == "scope_split_recommended" ]]
  [[ -f .git/pr-loop/pr-scope.json ]]
}

@test "refuses to overwrite different PR" {
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  run bash "${SCRIPTS}/state_init.sh" o r 99
  [[ "$status" -eq 5 ]]
  [[ "$output" == *"different PR"* ]]
}

@test "usage error exits 2" {
  run bash "${SCRIPTS}/state_init.sh"
  [[ "$status" -eq 2 ]]
}

@test "helper sourcing failure exits 6 with remediation hint" {
  ADVERSARY_CAP=999 run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 6 ]]
  [[ "$output" == *"failed to source"* ]]
  [[ "$output" == *"unset it and retry"* ]]
}

@test "ADVERSARY_CAP vs schema mismatch exits 6" {
  # Stub jq so any schema-maximum read returns a value that disagrees with
  # ADVERSARY_CAP=2 from scripts/_adversary_caps.sh. The rest of state_init's
  # jq calls (which take --argjson / --arg flags) pass through to real jq via
  # the absolute path captured in setup() — `command -v jq` at stub run-time
  # would resolve back to the stub itself.
  stub_cmd jq "
    if [[ \"\$*\" == *.maximum* ]]; then
      echo 999
      exit 0
    fi
    exec \"${REAL_JQ}\" \"\$@\"
  "
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 6 ]]
  [[ "$output" == *"disagrees with schema maximum"* ]]
}

@test "ADVERSARY_CAP vs schema mismatch on second field exits 6 and names that field" {
  # Pins that scripts/state_init.sh iterates BOTH schema fields. A refactor
  # that collapsed the `for FIELD in …` loop to a single field would still
  # pass the symmetric-stub mismatch test above (because the stub returns a
  # uniform value), so this asymmetric stub returns 2 for the first field
  # (matching ADVERSARY_CAP) and 3 for the second to force the second
  # iteration's branch.
  stub_cmd jq "
    if [[ \"\$*\" == *shallow_approval_adversary_runs.maximum* ]]; then
      echo 3
      exit 0
    elif [[ \"\$*\" == *shallow_adversary_runs.maximum* ]]; then
      echo 2
      exit 0
    fi
    exec \"${REAL_JQ}\" \"\$@\"
  "
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 6 ]] || {
    echo "expected exit 6, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"shallow_approval_adversary_runs"* ]] || {
    echo "expected error to name shallow_approval_adversary_runs, got: $output"
    return 1
  }
}

@test "missing _adversary_caps.sh helper exits 6" {
  # Copy state_init.sh into an isolated dir WITHOUT the _adversary_caps.sh
  # helper alongside it. state_init.sh resolves HERE via `dirname "$0"`, so
  # the helper lookup at "${HERE}/_adversary_caps.sh" will fail. Without the
  # readability guard added to state_init.sh, `set -euo pipefail` would trip
  # on the `.` builtin and exit 1 — silently bypassing the documented exit-6
  # ladder. This test pins the guard so a future refactor can't regress it.
  local fake_scripts="${BATS_TEST_TMPDIR}/fake_scripts"
  mkdir -p "$fake_scripts"
  cp "${SCRIPTS}/state_init.sh" "${fake_scripts}/state_init.sh"
  # state_init.sh also reads templates/state.schema.json via "${HERE}/../templates".
  # The guard runs BEFORE that read, so the missing templates dir doesn't matter
  # here — but the test fails fast if the guard regresses and we fall through.
  run bash "${fake_scripts}/state_init.sh" o r 42
  [[ "$status" -eq 6 ]] || {
    echo "expected exit 6, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"cannot read"* && "$output" == *"_adversary_caps.sh"* ]] || {
    echo "expected 'cannot read' + helper filename in stderr, got: $output"
    return 1
  }
}

@test "schema cap unreadable (jq returns null) exits 6 with field-name error" {
  # When jq -r prints "null" (the path was renamed or removed), the guard at
  # scripts/state_init.sh's `[[ ! "$SCHEMA_CAP" =~ ^[0-9]+$ ]]` must trip and
  # surface the field-name in stderr — distinct from the value-mismatch path
  # which says "disagrees with schema maximum".
  stub_cmd jq "
    if [[ \"\$*\" == *.maximum* ]]; then
      echo null
      exit 0
    fi
    exec \"${REAL_JQ}\" \"\$@\"
  "
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 6 ]] || {
    echo "expected exit 6, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"could not read"* && "$output" == *"shallow_adversary_runs.maximum"* ]] || {
    echo "expected 'could not read .properties.shallow_adversary_runs.maximum' in output, got: $output"
    return 1
  }
}

@test "writes loop_started_at as ISO 8601 UTC timestamp" {
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  run jq -r '.loop_started_at' .git/pr-loop/state.json
  [[ "$status" -eq 0 ]]
  [[ "$output" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
}

@test "non-positive max_iterations exits 2" {
  run bash "${SCRIPTS}/state_init.sh" o r 42 0
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"max_iterations must be >= 1"* ]]
}

@test "helper failure does not leave a partial state file behind" {
  run bash "${SCRIPTS}/state_init.sh" o r 42 0
  [[ "$status" -eq 2 ]]
  [[ ! -e .git/pr-loop/state.json ]]
}

@test "persists default knob values so Step 5 terminal metric reflects real state" {
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  # SKILL.md Step 5 reads these fields for the terminal metric `knobs` block.
  # If state_init does not write them, every record logs the same default and
  # scenario 21 check 3 trivially passes.
  jq -e '
    .pr_scope_mode == "auto" and
    .max_new_loc == 1000 and
    .approvers_required == "all" and
    (.approvers_required_list | length) == 11 and
    (.approvers_required_list[-1] == "blind_spots") and
    .suggestion_promotion_threshold == 2 and
    .adversary_promotion == true and
    .adversary_solo_promotion == true and
    .adversary_panel_visibility == "full" and
    .shallow_adversary_runs == 0 and
    (has("shallow_approval_adversary_runs") | not)
  ' .git/pr-loop/state.json
}

@test "dry_run=true is persisted in state" {
  run bash "${SCRIPTS}/state_init.sh" o r 42 15 true
  [[ "$status" -eq 0 ]]
  jq -e '.dry_run == true' .git/pr-loop/state.json
}

@test "dry_run defaults to false when omitted" {
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  jq -e '.dry_run == false' .git/pr-loop/state.json
}

@test "a non-literal dry_run value is rejected rather than treated as false" {
  # This argument gates the no-write path, so a typo must fail setup instead of
  # silently enabling commit/push.
  for bad in True tru yes 1; do
    run bash "${SCRIPTS}/state_init.sh" o r 42 15 "$bad"
    [[ "$status" -eq 2 ]]
    [[ "$output" == *"must be exactly"* ]]
  done
}
