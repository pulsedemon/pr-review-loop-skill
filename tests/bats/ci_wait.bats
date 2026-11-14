#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
}

@test "all checks pass returns 0" {
  stub_cmd gh 'echo "[{\"name\":\"build\",\"state\":\"SUCCESS\",\"bucket\":\"pass\",\"link\":\"\"}]"'
  run bash "${SCRIPTS}/ci_wait.sh" 42 5 1
  [[ "$status" -eq 0 ]]
}

@test "any failed check returns 1" {
  stub_cmd gh 'echo "[{\"name\":\"build\",\"state\":\"FAILURE\",\"bucket\":\"fail\",\"link\":\"https://x\"}]"'
  run bash "${SCRIPTS}/ci_wait.sh" 42 5 1
  [[ "$status" -eq 1 ]]
}

@test "failed check alongside a pending check returns 1 (not a timeout)" {
  stub_cmd gh 'echo "[{\"name\":\"build\",\"state\":\"FAILURE\",\"bucket\":\"fail\",\"link\":\"https://x\"},{\"name\":\"lint\",\"state\":\"IN_PROGRESS\",\"bucket\":\"pending\",\"link\":\"\"}]"'
  run bash "${SCRIPTS}/ci_wait.sh" 42 5 1
  [[ "$status" -eq 1 ]]
}

@test "gh failure with non-JSON stderr exits 5 and writes gh_error summary" {
  stub_cmd gh 'echo "HTTP 401: Bad credentials" >&2; exit 1'
  run bash "${SCRIPTS}/ci_wait.sh" 42 5 1
  [[ "$status" -eq 5 ]]
  test -f .git/pr-loop/last_ci_status.json
  run jq -e '.status == "gh_error"' .git/pr-loop/last_ci_status.json
  [[ "$status" -eq 0 ]]
  run jq -e '.error | contains("HTTP 401")' .git/pr-loop/last_ci_status.json
  [[ "$status" -eq 0 ]]
}

@test "no checks reported routes to exit 4 with no_checks summary" {
  stub_cmd gh 'echo "no checks reported on the feature branch" >&2; exit 1'
  run bash "${SCRIPTS}/ci_wait.sh" 42 30 0
  [[ "$status" -eq 4 ]]
  test -f .git/pr-loop/last_ci_status.json
  run jq -e '.status == "no_checks"' .git/pr-loop/last_ci_status.json
  [[ "$status" -eq 0 ]]
}

@test "usage error exits 3" {
  run bash "${SCRIPTS}/ci_wait.sh"
  [[ "$status" -eq 3 ]]
}
