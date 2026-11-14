#!/usr/bin/env bats
# tests/bats/test_append_metric.bats — cover scripts/append_metric.py.

load test_helper

setup() {
  make_tmp_repo
  SCRIPT="${SCRIPTS}/append_metric.py"
}

@test "appends a single line for a single object" {
  echo '{"kind":"iteration","iteration":1}' | python3 "$SCRIPT"
  [ "$?" -eq 0 ]
  run wc -l < .git/pr-loop/metrics.jsonl
  [ "$status" -eq 0 ]
  # exact equality (after trimming whitespace) — `=~ 1` would also accept 10, 11, 21, ...
  [ "${output// /}" = "1" ]
}

@test "two invocations produce two lines" {
  echo '{"kind":"iteration","iteration":1}' | python3 "$SCRIPT"
  echo '{"kind":"iteration","iteration":2}' | python3 "$SCRIPT"
  run wc -l < .git/pr-loop/metrics.jsonl
  [ "${output// /}" = "2" ]
}

@test "rejects non-JSON stdin with exit 2" {
  run bash -c "echo 'not json' | python3 '$SCRIPT'"
  [ "$status" -eq 2 ]
}

@test "rejects a JSON array (must be an object) with exit 2" {
  run bash -c "echo '[1,2,3]' | python3 '$SCRIPT'"
  [ "$status" -eq 2 ]
}

@test "exits 1 outside a git repo" {
  cd "${BATS_TEST_TMPDIR}"
  mkdir -p outside
  cd outside
  run bash -c "echo '{}' | python3 '$SCRIPT'"
  [ "$status" -eq 1 ]
}

@test "creates .git/pr-loop/ if missing" {
  [ ! -d .git/pr-loop ]
  echo '{}' | python3 "$SCRIPT"
  [ -d .git/pr-loop ]
  [ -f .git/pr-loop/metrics.jsonl ]
}

@test "rejects NaN constant with exit 2" {
  # json.loads accepts NaN by default; downstream jq cannot parse it, so we
  # must reject it loudly rather than write an unparseable line.
  run bash -c "echo '{\"v\": NaN}' | python3 '$SCRIPT'"
  [ "$status" -eq 2 ]
}

@test "rejects Infinity constant with exit 2" {
  run bash -c "echo '{\"v\": Infinity}' | python3 '$SCRIPT'"
  [ "$status" -eq 2 ]
}

@test "round-trips non-ASCII payload under LANG=C" {
  LANG=C LC_ALL=C run bash -c "printf '%s\n' '{\"label\":\"\\u2728 ok\"}' | python3 '$SCRIPT'"
  [ "$status" -eq 0 ]
  run jq -r '.label' < .git/pr-loop/metrics.jsonl
  [ "$status" -eq 0 ]
  [ "$output" = "✨ ok" ]
}
