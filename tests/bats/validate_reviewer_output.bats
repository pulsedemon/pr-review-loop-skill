#!/usr/bin/env bats

load test_helper

@test "valid reviewer output passes" {
  run bash -c "echo '{\"reviewer\":\"correctness\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "dispatched reviewer identity passes for matching stdin response" {
  run bash -c 'printf "%s" "$1" | python3 "$2/validate_reviewer_output.py" --reviewer tests' _ '{"reviewer":"tests","verdict":"approve","findings":[]}' "$SCRIPTS"
  [[ "$status" -eq 0 ]]
}

@test "dispatched reviewer identity rejects another valid persona response" {
  run bash -c 'printf "%s" "$1" | python3 "$2/validate_reviewer_output.py" --reviewer tests' _ '{"reviewer":"security","verdict":"approve","findings":[]}' "$SCRIPTS"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"expected reviewer 'tests', got 'security'"* ]]
}

@test "validator fails when schema \$id is missing or unexpected" {
  copy_skill_tree
  python3 -c "import json, pathlib; p = pathlib.Path('${BATS_TEST_TMPDIR}/skill/reviewers/output.schema.json'); s = json.loads(p.read_text()); s.pop('\$id', None); p.write_text(json.dumps(s))"
  run bash -c "echo '{\"reviewer\":\"correctness\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${BATS_TEST_TMPDIR}/skill/scripts/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"\$id"* ]]
}

@test "validator fails when schema \$id has wrong prefix" {
  copy_skill_tree
  python3 -c "import json, pathlib; p = pathlib.Path('${BATS_TEST_TMPDIR}/skill/reviewers/output.schema.json'); s = json.loads(p.read_text()); s['\$id'] = 'https://example.com/wrong/v0.1.0'; p.write_text(json.dumps(s))"
  run bash -c "echo '{\"reviewer\":\"correctness\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${BATS_TEST_TMPDIR}/skill/scripts/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"\$id"* ]]
}

@test "validator fails when schema \$id has wrong version under right prefix" {
  copy_skill_tree
  python3 -c "import json, pathlib; p = pathlib.Path('${BATS_TEST_TMPDIR}/skill/reviewers/output.schema.json'); s = json.loads(p.read_text()); s['\$id'] = 'https://github.com/pulsedemon/pr-review-loop-skill/schemas/reviewer-output/0.2.0.json'; p.write_text(json.dumps(s))"
  run bash -c "echo '{\"reviewer\":\"correctness\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${BATS_TEST_TMPDIR}/skill/scripts/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"\$id"* ]]
}

@test "missing reviewer field fails" {
  run bash -c "echo '{\"verdict\":\"approve\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"'reviewer' is a required property"* ]]
}

@test "bad verdict enum fails" {
  run bash -c "echo '{\"reviewer\":\"correctness\",\"verdict\":\"approved\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"verdict"* ]]
}

@test "unknown reviewer name fails" {
  run bash -c "echo '{\"reviewer\":\"securty\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"reviewer"* ]]
}

@test "finding with bad severity fails" {
  local payload='{"reviewer":"correctness","verdict":"request_changes","findings":[{"severity":"critical","scope":"in_scope","summary":"x","file":"a","line":1,"detail":"d"}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"severity"* ]]
}

@test "in_scope finding without file/line/detail fails" {
  local payload='{"reviewer":"correctness","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","summary":"x"}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  # error should mention one of the required fields
  [[ "$output" == *"file"* || "$output" == *"line"* || "$output" == *"detail"* ]]
}

@test "out_of_scope finding without file/line/detail passes" {
  local payload='{"reviewer":"correctness","verdict":"comment","findings":[{"severity":"suggestion","scope":"out_of_scope","summary":"x"}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "in_scope finding with all required fields passes" {
  local payload='{"reviewer":"security","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","summary":"x","file":"app.ts","line":42,"detail":"why"}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "malformed JSON fails" {
  run bash -c "echo 'not json' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"invalid JSON"* ]]
}

@test "adversary reviewer name passes" {
  run bash -c "echo '{\"reviewer\":\"adversary\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "comments reviewer name passes" {
  run bash -c "echo '{\"reviewer\":\"comments\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "blind_spots reviewer name passes" {
  run bash -c "echo '{\"reviewer\":\"blind_spots\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "blindspots (no underscore) is rejected as unknown reviewer name" {
  # The generic "unknown reviewer name fails" test covers `securty` for the
  # pre-existing enum. The new `blind_spots` value deserves its own
  # negative case so a future enum regression that accepts a near-miss
  # spelling can't escape this suite. `blindspots` is the most plausible
  # typo (matches the prose spelling without underscore) and would silently
  # bypass the manifest enum.
  run bash -c "echo '{\"reviewer\":\"blindspots\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"reviewer"* ]]
}

@test "blind_spots reviewer in_scope (b2) silent-pass request_changes payload passes" {
  # Canonical request_changes payload for the new enum value. The
  # approve+empty positive above proves the enum accepts the name; this
  # proves the schema also accepts the realistic shape blind_spots emits
  # for its category-(b) findings — severity, scope, file, line, detail,
  # finding_evidence with file+line+snippet.
  local payload='{"reviewer":"blind_spots","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","summary":"validator exits 0 when no jq is available (b2: silent pass)","file":"scripts/run_local_validation.sh","line":42,"detail":"detect_stack returns success when jq absent; missing-tool path returns exit 0 instead of exit 1, masking validation gap","finding_evidence":{"file":"scripts/run_local_validation.sh","line":42,"snippet":"command -v jq >/dev/null 2>&1 || return 0"}}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "comments reviewer in_scope blocker passes" {
  local payload='{"reviewer":"comments","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","summary":"docstring claims returns null on miss but code now throws","file":"src/cache.ts","line":17,"detail":"docstring: \"returns null when key absent\"; code throws NotFoundError on miss"}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "error_handling reviewer name passes" {
  run bash -c "echo '{\"reviewer\":\"error_handling\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "error_handling reviewer blocker with finding_evidence passes" {
  local payload='{"reviewer":"error_handling","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","summary":"bare except hides KeyError and TimeoutError","file":"src/fetch.py","line":42,"detail":"could hide KeyError, TimeoutError, KeyboardInterrupt; user sees empty list, nothing logged","finding_evidence":{"file":"src/fetch.py","line":42,"snippet":"except Exception: pass"}}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "type_design reviewer name passes" {
  run bash -c "echo '{\"reviewer\":\"type_design\",\"verdict\":\"approve\",\"findings\":[]}' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "type_design reviewer blocker with suggested_fix passes" {
  local payload='{"reviewer":"type_design","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","summary":"mutually exclusive flags both representable as true","file":"src/order.ts","line":12,"detail":"isPending and isComplete are independent booleans; both can be true at once although methods treat them as exclusive","suggested_fix":"replace with status: \"pending\" | \"complete\" | \"failed\" discriminated union"}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "finding with finding_evidence (file+line+symbol) passes" {
  local payload='{"reviewer":"tests","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","file":"src/a.ts","line":10,"summary":"test name claims X but asserts Y","detail":"see body","finding_evidence":{"file":"tests/a.test.ts","line":42,"symbol":"test_x_behavior"}}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "finding with finding_evidence (file+line+snippet) passes" {
  local payload='{"reviewer":"tests","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","file":"src/a.ts","line":10,"summary":"s","detail":"d","finding_evidence":{"file":"tests/a.test.ts","line":42,"snippet":"expect(result).toBe(0)"}}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "finding_evidence with neither symbol nor snippet fails" {
  local payload='{"reviewer":"tests","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","file":"src/a.ts","line":10,"summary":"s","detail":"d","finding_evidence":{"file":"tests/a.test.ts","line":42}}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
}

@test "finding_evidence with line < 1 fails" {
  local payload='{"reviewer":"tests","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","file":"src/a.ts","line":10,"summary":"s","detail":"d","finding_evidence":{"file":"tests/a.test.ts","line":0,"symbol":"x"}}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
}

@test "finding_evidence with unknown property fails" {
  local payload='{"reviewer":"tests","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","file":"src/a.ts","line":10,"summary":"s","detail":"d","finding_evidence":{"file":"tests/a.test.ts","line":42,"symbol":"x","bogus":true}}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
}

@test "finding with move_b_pattern but no finding_evidence passes" {
  local payload='{"reviewer":"correctness","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","file":"src/a.ts","line":10,"summary":"second instance of missing required","detail":"d","move_b_pattern":"missing required on schema entry"}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}

@test "move_b_pattern wrong type fails" {
  local payload='{"reviewer":"correctness","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","file":"src/a.ts","line":10,"summary":"s","detail":"d","move_b_pattern":42}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 1 ]]
}

@test "finding without finding_evidence still passes (backward compat)" {
  local payload='{"reviewer":"correctness","verdict":"request_changes","findings":[{"severity":"blocker","scope":"in_scope","file":"src/a.ts","line":10,"summary":"s","detail":"d"}]}'
  run bash -c "echo '$payload' | python3 ${SCRIPTS}/validate_reviewer_output.py"
  [[ "$status" -eq 0 ]]
}
