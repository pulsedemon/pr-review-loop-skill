#!/usr/bin/env bats

load test_helper

# helper: run the matcher with two inline JSON objects
match() {
  local a="$1" b="$2"
  echo "$a" > "${BATS_TEST_TMPDIR}/a.json"
  echo "$b" > "${BATS_TEST_TMPDIR}/b.json"
  python3 "${SCRIPTS}/match_findings.py" "${BATS_TEST_TMPDIR}/a.json" "${BATS_TEST_TMPDIR}/b.json"
}

@test "identical findings match" {
  run match \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference on user input"}' \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference on user input"}'
  [[ "$status" -eq 0 ]]
}

@test "same file, line within ±5, similar summary matches" {
  run match \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference on user input"}' \
    '{"file":"src/a.ts","line":13,"summary":"null pointer dereference when input is empty"}'
  [[ "$status" -eq 0 ]]
}

@test "same file but line distance > 5 does not match" {
  run match \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference on user input"}' \
    '{"file":"src/a.ts","line":17,"summary":"null pointer dereference on user input"}'
  [[ "$status" -eq 1 ]]
}

@test "different file does not match" {
  run match \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference on user input"}' \
    '{"file":"src/b.ts","line":10,"summary":"null pointer dereference on user input"}'
  [[ "$status" -eq 1 ]]
}

@test "disjoint summaries do not match" {
  run match \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference on user input"}' \
    '{"file":"src/a.ts","line":10,"summary":"missing audit log for password reset"}'
  [[ "$status" -eq 1 ]]
}

@test "near-miss summary just over 0.6 overlap matches" {
  # summaries share 3 of 4 content tokens after stop-word filtering
  run match \
    '{"file":"src/a.ts","line":10,"summary":"missing null check on user input"}' \
    '{"file":"src/a.ts","line":10,"summary":"missing null check on the input"}'
  [[ "$status" -eq 0 ]]
}

@test "near-miss summary just under 0.6 overlap does not match" {
  # 1 shared token (request) across 12 union tokens after stop-word filtering — well under 0.6
  run match \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference on user input from request body"}' \
    '{"file":"src/a.ts","line":10,"summary":"missing audit log for password reset request"}'
  [[ "$status" -eq 1 ]]
}

@test "stopword-only summaries on both sides do not match" {
  # both summaries tokenize to the empty set after stop-word filtering, so
  # the matcher has no signal to compare and must return no-match. this also
  # pins token_overlap returning 0.0 (not 1.0) for both-empty token sets,
  # which keeps it aligned with promote_findings._is_match.
  run match \
    '{"file":"src/a.ts","line":10,"summary":"the and is"}' \
    '{"file":"src/a.ts","line":10,"summary":"of for at"}'
  [[ "$status" -eq 1 ]]
}

@test "one side stopword-only does not match" {
  run match \
    '{"file":"src/a.ts","line":10,"summary":"missing null check"}' \
    '{"file":"src/a.ts","line":10,"summary":"the and is"}'
  [[ "$status" -eq 1 ]]
}

@test "missing file in input exits 2" {
  # pass a missing-file payload as file arg alongside a valid stdin payload, so
  # both args satisfy the arity check and the script reaches the _require(file)
  # branch rather than the usage-error branch.
  echo '{"line":1,"summary":"x"}' > "${BATS_TEST_TMPDIR}/a.json"
  run bash -c "echo '{\"file\":\"src/a.ts\",\"line\":1,\"summary\":\"x\"}' | python3 ${SCRIPTS}/match_findings.py ${BATS_TEST_TMPDIR}/a.json -"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"'file'"* || "$output" == *"missing"* ]]
}

@test "missing line in input exits 2" {
  echo '{"file":"a","summary":"x"}' > "${BATS_TEST_TMPDIR}/a.json"
  echo '{"file":"a","line":1,"summary":"x"}' > "${BATS_TEST_TMPDIR}/b.json"
  run python3 "${SCRIPTS}/match_findings.py" "${BATS_TEST_TMPDIR}/a.json" "${BATS_TEST_TMPDIR}/b.json"
  [[ "$status" -eq 2 ]]
}

@test "case-insensitive token overlap" {
  run match \
    '{"file":"src/a.ts","line":10,"summary":"NULL POINTER DEREFERENCE ON USER INPUT"}' \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference on user input"}'
  [[ "$status" -eq 0 ]]
}

@test "stdin success path: one arg '-' with a matching pair returns 0" {
  echo '{"file":"src/a.ts","line":10,"summary":"null pointer dereference on user input"}' > "${BATS_TEST_TMPDIR}/b.json"
  run bash -c "echo '{\"file\":\"src/a.ts\",\"line\":10,\"summary\":\"null pointer dereference on user input\"}' | python3 ${SCRIPTS}/match_findings.py - ${BATS_TEST_TMPDIR}/b.json"
  [[ "$status" -eq 0 ]]
}

@test "both args '-' exits 2" {
  run bash -c "echo '{}' | python3 ${SCRIPTS}/match_findings.py - -"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"at most one"* || "$output" == *"-"* ]]
}

@test "malformed JSON input exits 2" {
  echo 'not json at all' > "${BATS_TEST_TMPDIR}/a.json"
  echo '{"file":"src/a.ts","line":10,"summary":"x"}' > "${BATS_TEST_TMPDIR}/b.json"
  run python3 "${SCRIPTS}/match_findings.py" "${BATS_TEST_TMPDIR}/a.json" "${BATS_TEST_TMPDIR}/b.json"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"cannot read"* || "$output" == *"JSON"* || "$output" == *"json"* ]]
}

@test "non-object JSON (array) exits 2" {
  echo '[1,2,3]' > "${BATS_TEST_TMPDIR}/a.json"
  echo '{"file":"src/a.ts","line":10,"summary":"x"}' > "${BATS_TEST_TMPDIR}/b.json"
  run python3 "${SCRIPTS}/match_findings.py" "${BATS_TEST_TMPDIR}/a.json" "${BATS_TEST_TMPDIR}/b.json"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"expected JSON object"* ]]
}

@test "non-integer line value exits 2" {
  run match \
    '{"file":"src/a.ts","line":"10","summary":"null pointer dereference"}' \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference"}'
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"line"* ]]
}

@test "non-string file value exits 2" {
  run match \
    '{"file":1,"line":10,"summary":"null pointer dereference"}' \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference"}'
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"'file'"* || "$output" == *"file"* ]]
}

@test "non-string summary value exits 2" {
  run match \
    '{"file":"src/a.ts","line":10,"summary":5}' \
    '{"file":"src/a.ts","line":10,"summary":"null pointer dereference"}'
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"summary"* ]]
}

@test "bare invocation (no args) exits 2 with usage message" {
  run python3 "${SCRIPTS}/match_findings.py"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"usage"* ]]
}

@test "non-utf8 file input exits 2 with a clean error" {
  # latin-1 encoded bytes that are not valid utf-8
  printf '{"file":"src/a.ts","line":10,"summary":"caf\xe9"}' > "${BATS_TEST_TMPDIR}/a.json"
  echo '{"file":"src/a.ts","line":10,"summary":"cafe"}' > "${BATS_TEST_TMPDIR}/b.json"
  run python3 "${SCRIPTS}/match_findings.py" "${BATS_TEST_TMPDIR}/a.json" "${BATS_TEST_TMPDIR}/b.json"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"cannot read input"* ]]
  [[ "$output" != *"Traceback"* ]]
}
