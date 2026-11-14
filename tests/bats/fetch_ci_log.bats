#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
}

@test "exits 1 on usage error" {
  run bash "${SCRIPTS}/fetch_ci_log.sh"
  [[ "$status" -eq 1 ]]
}

@test "exits 5 when check not found" {
  stub_cmd gh 'echo "[]"'
  run bash "${SCRIPTS}/fetch_ci_log.sh" 42 nope
  [[ "$status" -eq 5 ]]
  [[ "$output" == *"no check named"* ]]
}

@test "exits 3 when link unparseable" {
  stub_cmd gh 'echo "[{\"name\":\"build\",\"bucket\":\"fail\",\"link\":\"https://example.com/no-run-id\"}]"'
  run bash "${SCRIPTS}/fetch_ci_log.sh" 42 build
  [[ "$status" -eq 3 ]]
}

@test "failing checks (gh exits non-zero with valid JSON) still resolve the link" {
  stub_cmd gh 'case "$1" in
    "pr")
      echo "[{\"name\":\"build\",\"bucket\":\"fail\",\"link\":\"https://github.com/o/r/actions/runs/5/job/9\"}]"
      exit 1 ;;
    "run")
      echo "build failed: boom"
      exit 0 ;;
  esac'
  run bash "${SCRIPTS}/fetch_ci_log.sh" 42 build
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"boom"* ]]
}

@test "selects the failing job when a passing check has the same name" {
  stub_cmd gh 'case "$1 $2" in
    "pr checks")
      [[ "$*" == *"--json name,link,bucket"* ]] || exit 99
      echo "[{\"name\":\"build\",\"bucket\":\"pass\",\"link\":\"https://github.com/o/r/actions/runs/1/job/2\"},{\"name\":\"build\",\"bucket\":\"fail\",\"link\":\"https://github.com/o/r/actions/runs/5/job/9\"}]"
      exit 1 ;;
    "run view")
      [[ "$3" == 5 && "$4" == --log-failed && "$5" == --job && "$6" == 9 ]] || exit 99
      echo "failing job log" ;;
    *) exit 99 ;;
  esac'

  run bash "${SCRIPTS}/fetch_ci_log.sh" 42 build

  [[ "$status" -eq 0 ]]
  [[ "$output" == "failing job log" ]]
}

@test "selects the cancelled job when a passing check has the same name" {
  stub_cmd gh 'case "$1 $2" in
    "pr checks")
      echo "[{\"name\":\"build\",\"bucket\":\"pass\",\"link\":\"https://github.com/o/r/actions/runs/1/job/2\"},{\"name\":\"build\",\"bucket\":\"cancel\",\"link\":\"https://github.com/o/r/actions/runs/5/job/9\"}]"
      exit 1 ;;
    "run view")
      [[ "$3" == 5 && "$4" == --log-failed && "$5" == --job && "$6" == 9 ]] || exit 99
      echo "cancelled job log" ;;
    *) exit 99 ;;
  esac'

  run bash "${SCRIPTS}/fetch_ci_log.sh" 42 build

  [[ "$status" -eq 0 ]]
  [[ "$output" == "cancelled job log" ]]
}

@test "exits 5 without reading a passing job when no matching failed check exists" {
  stub_cmd gh 'case "$1 $2" in
    "pr checks")
      echo "[{\"name\":\"build\",\"bucket\":\"pass\",\"link\":\"https://github.com/o/r/actions/runs/1/job/2\"},{\"name\":\"other\",\"bucket\":\"fail\",\"link\":\"https://github.com/o/r/actions/runs/5/job/9\"}]"
      exit 1 ;;
    *) touch "$BATS_TEST_TMPDIR/log-requested"; exit 99 ;;
  esac'

  run bash "${SCRIPTS}/fetch_ci_log.sh" 42 build

  [[ "$status" -eq 5 ]]
  [[ "$output" == *"no check named"* ]]
  [[ ! -e "$BATS_TEST_TMPDIR/log-requested" ]]
}

@test "exits 5 when gh returns no JSON (genuine gh failure)" {
  stub_cmd gh 'exit 1'
  run bash "${SCRIPTS}/fetch_ci_log.sh" 42 build
  [[ "$status" -eq 5 ]]
  [[ "$output" == *"no JSON"* ]]
}

@test "surfaces gh's stderr on the no-JSON failure path (not just /dev/null)" {
  # A genuine gh failure prints its cause to stderr and no JSON to stdout. The
  # script must echo that cause rather than discard it, so an auth/rate-limit
  # outage is not misread as a missing check.
  stub_cmd gh 'echo "HTTP 401: Bad credentials (gh auth login)" >&2; exit 1'
  run bash "${SCRIPTS}/fetch_ci_log.sh" 42 build
  [[ "$status" -eq 5 ]]
  [[ "$output" == *"no JSON"* ]]
  [[ "$output" == *"Bad credentials"* ]]
}
