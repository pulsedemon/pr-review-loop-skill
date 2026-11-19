#!/usr/bin/env bats

load test_helper

setup() {
  # capture jq before installing stubs so their pass-through fallback
  # cannot resolve back to the stub itself.
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
  # a transient gh/auth failure must not mask valid resumable state.
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

@test "refuses to overwrite an unfinished loop for a different PR" {
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  run bash "${SCRIPTS}/state_init.sh" o r 99
  [[ "$status" -eq 5 ]]
  [[ "$output" == *"unfinished loop for a different PR (#42)"* ]]
  [[ "$(jq -r .pr_number .git/pr-loop/state.json)" == "42" ]]
}

@test "a completed loop's state for a different PR is replaced" {
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  local state=".git/pr-loop/state.json"
  jq '.status = "success" | .iteration = 3 | .completed_at = "2026-09-10T17:00:00Z"' "$state" > "$state.tmp" && mv "$state.tmp" "$state"
  echo '{}' > .git/pr-loop/pr-scope.json
  stub_cmd gh 'cat <<JSON
{"number":99,"title":"Other","url":"https://github.com/o/r/pull/99","headRefName":"other","baseRefName":"main","headRefOid":"cafef00d","body":"","isDraft":false}
JSON'
  run bash "${SCRIPTS}/state_init.sh" o r 99
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"PR #42 completed"* ]]
  jq -e '.pr_number == 99 and .head_branch == "other" and .status == "running" and .iteration == 0
    and (has("completed_at") | not)' "$state"
  [[ ! -f .git/pr-loop/pr-scope.json ]]
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
  # let the first field match so a skipped second field cannot pass through
  # the symmetric stub's first-field failure.
  stub_cmd jq "
    if [[ \"\$*\" == *shallow_approval_adversary_runs.maximum* ]]; then
      echo 999
      exit 0
    elif [[ \"\$*\" == *shallow_adversary_runs.maximum* ]]; then
      echo $(python3 -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["cap"])' "${REPO_ROOT}/manifests/adversary-caps.yaml")
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
  # sourcing a missing helper under set -e would exit 1, losing the
  # documented exit 6 and its diagnostic.
  local fake_scripts="${BATS_TEST_TMPDIR}/fake_scripts"
  mkdir -p "$fake_scripts"
  cp "${SCRIPTS}/state_init.sh" "${fake_scripts}/state_init.sh"
  # the helper guard precedes the schema read, so no templates are needed.
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
  # an unreadable maximum must name its field, separately from a value mismatch.
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
  # absent fields make terminal metrics report fallback values instead of
  # the configuration used by this loop.
  jq -e '
    .pr_scope_mode == "auto" and
    .max_new_loc == 1000 and
    .approvers_required == "all" and
    (.approvers_required_list | length) == 11 and
    (.approvers_required_list[-1] == "blind_spots") and
    .suggestion_promotion_threshold == 0 and
    .adversary_promotion == false and
    .adversary_solo_promotion == false and
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
  # this argument gates the no-write path, so a typo must fail setup instead of
  # silently enabling commit/push.
  for bad in True tru yes 1; do
    run bash "${SCRIPTS}/state_init.sh" o r 42 15 "$bad"
    [[ "$status" -eq 2 ]]
    [[ "$output" == *"must be exactly"* ]]
  done
}
