#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
}

@test "exits 2 when sonar CLI is missing" {
  assert_sonar_exits_2_missing_cli "fetch_sonar_gate.sh"
}

@test "exits 3 when sonar not authenticated" {
  assert_sonar_exits_3_not_authenticated "fetch_sonar_gate.sh"
}

@test "exits 1 on usage error" {
  assert_sonar_exits_1_usage_error "fetch_sonar_gate.sh"
}

# Serves $GATE_BODY for `sonar api get`, or fails like a server error when
# $SONAR_FAIL is set, and logs each api call to $SONAR_LOG.
stub_gate_sonar() {
  export GATE_BODY="$1" SONAR_FAIL="${2:-}"
  export SONAR_LOG="${BATS_TEST_TMPDIR}/sonar.log"
  : >"$SONAR_LOG"
  stub_cmd sonar '[[ "$1 $2" == "auth status" ]] && exit 0
echo "$*" >>"$SONAR_LOG"
if [[ -n "$SONAR_FAIL" ]]; then
  echo "HTTP 503 from server" >&2
  exit 1
fi
printf "%s" "$GATE_BODY"'
}

assert_unreadable_response() {
  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar_gate.sh" 42 proj
  [[ "$status" -eq 5 ]]
  [[ -z "$output" ]]
  [[ "$stderr" == *"unreadable quality gate response for project=proj pr=42"* ]]
}

@test "prints only the failing conditions for the requested project and pr" {
  stub_gate_sonar '{"projectStatus": {"status": "ERROR", "conditions": [
    {"status": "ERROR", "metricKey": "new_coverage"},
    {"status": "OK", "metricKey": "new_duplicated_lines_density"}]}}'

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar_gate.sh" 42 proj
  [[ "$status" -eq 0 ]]
  [[ "$(jq -c '[.[].metricKey]' <<<"$output")" == '["new_coverage"]' ]]
  grep -q 'projectKey=proj&pullRequest=42' "$SONAR_LOG"
}

@test "prints an empty array when the gate has no conditions" {
  stub_gate_sonar '{"projectStatus": {"status": "OK", "conditions": []}}'

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar_gate.sh" 42 proj
  [[ "$status" -eq 0 ]]
  [[ "$(jq -c . <<<"$output")" == '[]' ]]
}

@test "exits 5 with the CLI's error when the api call fails" {
  stub_gate_sonar '' fail

  bats_require_minimum_version 1.5.0
  run --separate-stderr bash "${SCRIPTS}/fetch_sonar_gate.sh" 42 proj
  [[ "$status" -eq 5 ]]
  [[ -z "$output" ]]
  [[ "$stderr" == *"HTTP 503 from server"* ]]
  [[ "$stderr" == *"project=proj pr=42"* ]]
}

@test "exits 5 on a response that is not JSON" {
  stub_gate_sonar 'warning: not json'
  assert_unreadable_response
}

@test "exits 5 on an empty response" {
  stub_gate_sonar ''
  assert_unreadable_response
}

@test "exits 5 when the response has no conditions field" {
  stub_gate_sonar '{"projectStatus": {"status": "OK"}}'
  assert_unreadable_response
}
