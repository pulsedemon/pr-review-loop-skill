#!/usr/bin/env bats

# scripts/check_exit_conditions.py owns the NO_PROGRESS and CI_STUCK
# comparisons that SKILL.md §4d and §4d.1 used to specify in prose. Nothing
# tested them before, because there was no code to test.
#
# Cases 2 and 3 are tests/scenarios/03-no-progress.md Variants A and B, which
# had never been run.

load test_helper

check_exit() {
  echo "$1" | python3 "${SCRIPTS}/check_exit_conditions.py" --state "$2"
}

# Write a state.json whose history[] is the given JSON array.
write_state() {
  local path="$1" history="$2"
  jq -nc --argjson h "$history" '{schema_version:1, iteration:(($h|length)+1), history:$h}' >"$path"
}

blocker() { # file line summary -> one finding object ("null" line = omitted)
  jq -nc --arg f "$1" --argjson l "$2" --arg s "$3" \
    'if $l == null then {reviewer:"correctness",severity:"blocker",scope:"in_scope",file:$f,summary:$s}
     else {reviewer:"correctness",severity:"blocker",scope:"in_scope",file:$f,line:$l,summary:$s} end'
}

status_of() { jq -r '.terminal_status' <<<"$1"; }

setup() {
  STATE="${BATS_TEST_TMPDIR}/state.json"
  SQL="sql injection query built by string concatenation"
  NULLDEREF="null deref on the parsed response"
}

@test "identical blocker repeated from history[-1] exits NO_PROGRESS" {
  local b; b=$(blocker "src/db.ts" 88 "$SQL")
  write_state "$STATE" "$(jq -nc --argjson b "$b" '[{iteration:1,findings:[$b]}]')"
  run check_exit "$(jq -nc --argjson b "$b" '{blockers:[$b]}')" "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$(status_of "$output")" == "NO_PROGRESS" ]]
}

@test "oscillating A/B/A blockers exit NO_PROGRESS via history[-2]" {
  # Scenario 03 Variant A: no two consecutive iterations match, so a
  # history[-1]-only comparison never fires and the loop runs to
  # MAX_ITERATIONS pushing a commit each time.
  local a b; a=$(blocker "src/parse.ts" 31 "$NULLDEREF"); b=$(blocker "src/db.ts" 88 "$SQL")
  write_state "$STATE" "$(jq -nc --argjson a "$a" --argjson b "$b" \
    '[{iteration:4,findings:[$a]},{iteration:5,findings:[$b]}]')"
  run check_exit "$(jq -nc --argjson a "$a" '{blockers:[$a]}')" "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$(status_of "$output")" == "NO_PROGRESS" ]]
  [[ "$output" == *"history[-2]"* ]]
}

@test "reworded blocker at a nearby line exits NO_PROGRESS" {
  # Scenario 03 Variant B. Assert the verdict, not the overlap score: pinning
  # the float would make a stop-word tweak fail here instead of in the
  # matcher's own tests.
  local prev cur
  prev=$(blocker "src/db.ts" 88 "SQL injection: query built by string concatenation")
  cur=$(blocker "src/db.ts" 89 "SQL injection: query built via string concatenation")
  write_state "$STATE" "$(jq -nc --argjson p "$prev" '[{iteration:1,findings:[$p]}]')"
  run check_exit "$(jq -nc --argjson c "$cur" '{blockers:[$c]}')" "$STATE"
  [[ "$(status_of "$output")" == "NO_PROGRESS" ]]
}

@test "repeated blocker with no line exits NO_PROGRESS via the summary fallback" {
  # The §4c matcher needs both file and line and returns false without them,
  # so this blocker would otherwise never match its own repeat.
  local b; b=$(blocker "src/db.ts" null "$SQL")
  write_state "$STATE" "$(jq -nc --argjson b "$b" '[{iteration:1,findings:[$b]}]')"
  run check_exit "$(jq -nc --argjson b "$b" '{blockers:[$b]}')" "$STATE"
  [[ "$(status_of "$output")" == "NO_PROGRESS" ]]
}

@test "same summary in different files does not exit" {
  local prev cur
  prev=$(blocker "src/a.ts" null "$SQL"); cur=$(blocker "src/b.ts" null "$SQL")
  write_state "$STATE" "$(jq -nc --argjson p "$prev" '[{iteration:1,findings:[$p]}]')"
  run check_exit "$(jq -nc --argjson c "$cur" '{blockers:[$c]}')" "$STATE"
  [[ "$(status_of "$output")" == "null" ]]
}

@test "line 0 is a location, not a missing line" {
  local prev cur
  prev=$(blocker "src/db.ts" 0 "$SQL"); cur=$(blocker "src/db.ts" 900 "$SQL")
  write_state "$STATE" "$(jq -nc --argjson p "$prev" '[{iteration:1,findings:[$p]}]')"
  run check_exit "$(jq -nc --argjson c "$cur" '{blockers:[$c]}')" "$STATE"
  [[ "$(status_of "$output")" == "null" ]]
}

@test "a partially matching blocker set does not exit" {
  local a b; a=$(blocker "src/parse.ts" 31 "$NULLDEREF"); b=$(blocker "src/db.ts" 88 "$SQL")
  write_state "$STATE" "$(jq -nc --argjson a "$a" '[{iteration:1,findings:[$a]}]')"
  run check_exit "$(jq -nc --argjson a "$a" --argjson b "$b" '{blockers:[$a,$b]}')" "$STATE"
  [[ "$(status_of "$output")" == "null" ]]
}

@test "a shrinking blocker set is progress, not NO_PROGRESS" {
  # Three blockers down to one. One-way containment ("every current blocker
  # matches something previous") would wrongly fire here.
  local a b c
  a=$(blocker "src/parse.ts" 31 "$NULLDEREF")
  b=$(blocker "src/db.ts" 88 "$SQL")
  c=$(blocker "src/api.ts" 12 "unchecked error from the fetch call")
  write_state "$STATE" "$(jq -nc --argjson a "$a" --argjson b "$b" --argjson c "$c" \
    '[{iteration:1,findings:[$a,$b,$c]}]')"
  run check_exit "$(jq -nc --argjson a "$a" '{blockers:[$a]}')" "$STATE"
  [[ "$(status_of "$output")" == "null" ]]
}

@test "one blocker cannot stand in for two previous ones" {
  # Previous blockers at lines 10 and 20 are both within the match window of a
  # current one at 15. Two containment scans pass in both directions because
  # the single current blocker is reused, so a genuine 2 -> 1 shrink would read
  # as unchanged without one-to-one pairing.
  local p1 p2 cur
  p1=$(blocker "src/db.ts" 10 "$SQL")
  p2=$(blocker "src/db.ts" 20 "$SQL")
  cur=$(blocker "src/db.ts" 15 "$SQL")
  write_state "$STATE" "$(jq -nc --argjson a "$p1" --argjson b "$p2" \
    '[{iteration:1,findings:[$a,$b]}]')"
  run check_exit "$(jq -nc --argjson c "$cur" '{blockers:[$c]}')" "$STATE"
  [[ "$(status_of "$output")" == "null" ]]
}

@test "an unchanged two-blocker set still exits NO_PROGRESS regardless of order" {
  local a b
  a=$(blocker "src/db.ts" 88 "$SQL")
  b=$(blocker "src/parse.ts" 31 "$NULLDEREF")
  write_state "$STATE" "$(jq -nc --argjson a "$a" --argjson b "$b" \
    '[{iteration:1,findings:[$a,$b]}]')"
  run check_exit "$(jq -nc --argjson a "$a" --argjson b "$b" '{blockers:[$b,$a]}')" "$STATE"
  [[ "$(status_of "$output")" == "NO_PROGRESS" ]]
}

@test "a set matching neither entry alone does not exit" {
  # current {A,B}, history[-1]={B}, history[-2]={A}. Pooling the two entries
  # into one candidate set would fire on a set that repeats neither.
  local a b; a=$(blocker "src/parse.ts" 31 "$NULLDEREF"); b=$(blocker "src/db.ts" 88 "$SQL")
  write_state "$STATE" "$(jq -nc --argjson a "$a" --argjson b "$b" \
    '[{iteration:1,findings:[$a]},{iteration:2,findings:[$b]}]')"
  run check_exit "$(jq -nc --argjson a "$a" --argjson b "$b" '{blockers:[$a,$b]}')" "$STATE"
  [[ "$(status_of "$output")" == "null" ]]
}

@test "a malformed promoted record in history is skipped, not fatal" {
  # An unvalidated `file: []` makes the provenance key unhashable and crashes
  # a path documented as firing neither exit.
  local cur; cur=$(blocker "src/db.ts" 88 "$SQL")
  write_state "$STATE" "$(jq -nc --arg s "$SQL" \
    '[{iteration:1,findings:[],addressed:[{file:[],line:1,summary:$s,
       promoted_from:"suggestion",promoted_by:"multi-persona",source_reviewers:["a","b"]}]}]')"
  run check_exit "$(jq -nc --argjson b "$cur" '{blockers:[$b]}')" "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *"Traceback"* ]]
  [[ "$(status_of "$output")" == "null" ]]
}

@test "a blocker with a non-integer line exits 2" {
  # is_match coerces with int(), so "88" would match line 88 and true would
  # become line 1.
  write_state "$STATE" '[]'
  for bad in '"88"' 'true' '1.5'; do
    run bash -c "echo '{\"blockers\":[{\"severity\":\"blocker\",\"file\":\"a.ts\",\"line\":${bad},\"summary\":\"x y z\"}]}' |
      python3 '${SCRIPTS}/check_exit_conditions.py' --state '${STATE}'"
    [[ "$status" -eq 2 ]] || { echo "line=${bad} gave status ${status}"; return 1; }
  done
}

@test "a history entry with any malformed finding is unusable, not trimmed" {
  # Skipping the bad finding alone would leave {A}, which the current {A}
  # matches exactly, firing NO_PROGRESS on a set that really went 2 -> 1.
  local a; a=$(blocker "src/parse.ts" 31 "$NULLDEREF")
  write_state "$STATE" "$(jq -nc --argjson a "$a" --arg s "$SQL" \
    '[{iteration:1,findings:[$a,{reviewer:"correctness",severity:"blocker",scope:"in_scope",
       file:"src/db.ts",line:88,summary:123}]}]')"
  run check_exit "$(jq -nc --argjson a "$a" '{blockers:[$a]}')" "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$(status_of "$output")" == "null" ]]
}

@test "a history finding violating any required field makes the entry unusable" {
  # _well_formed has to cover every field the severity filter reads. A finding
  # that passes a partial check is dropped by the filter, and the smaller set
  # fires NO_PROGRESS on a blocker set that really shrank.
  local a; a=$(blocker "src/parse.ts" 31 "$NULLDEREF")
  local base='{reviewer:"correctness",severity:"blocker",scope:"in_scope",file:"src/db.ts",line:88,summary:"unchecked error from fetch"}'
  local mutation
  for mutation in '.severity="BLOCKER"' 'del(.severity)' 'del(.scope)' 'del(.reviewer)' '.scope="elsewhere"'; do
    write_state "$STATE" "$(jq -nc --argjson a "$a" --argjson bad "$(jq -nc "${base} | ${mutation}")" \
      '[{iteration:1,findings:[$a,$bad]}]')"
    run check_exit "$(jq -nc --argjson a "$a" '{blockers:[$a]}')" "$STATE"
    [[ "$(status_of "$output")" == "null" ]] || {
      echo "mutation ${mutation} still fired: $output"
      return 1
    }
  done
}

@test "a clean older entry is still reachable past an unusable newer one" {
  local a; a=$(blocker "src/parse.ts" 31 "$NULLDEREF")
  write_state "$STATE" "$(jq -nc --argjson a "$a" \
    '[{iteration:1,findings:[$a]},
      {iteration:2,findings:[$a,{reviewer:"correctness",severity:"blocker",scope:"in_scope",
       file:"src/db.ts",line:88,summary:123}]}]')"
  run check_exit "$(jq -nc --argjson a "$a" '{blockers:[$a]}')" "$STATE"
  [[ "$(status_of "$output")" == "NO_PROGRESS" ]]
  [[ "$output" == *"history[-2]"* ]]
}

@test "a persisted blocker with a non-integer line is not matched" {
  # is_match coerces with int(), so a persisted line of "88" would otherwise
  # match a current line 88 and fire off malformed history, which the docs
  # promise cannot happen.
  local cur; cur=$(blocker "src/db.ts" 88 "$SQL")
  write_state "$STATE" "$(jq -nc --arg s "$SQL" \
    '[{iteration:1,findings:[{reviewer:"correctness",severity:"blocker",scope:"in_scope",
       file:"src/db.ts",line:"88",summary:$s}]}]')"
  run check_exit "$(jq -nc --argjson b "$cur" '{blockers:[$b]}')" "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$(status_of "$output")" == "null" ]]
}

@test "a repeated promoted blocker exits NO_PROGRESS" {
  # promote_findings.py appends a promoted suggestion to blockers[] without
  # rewriting severity, so a severity-only filter drops it from the lookback
  # and an unchanged promoted blocker never fires. addressed[] is the
  # persisted record of exactly those promotions.
  local promoted
  promoted=$(jq -nc --arg s "$SQL" \
    '{reviewer:"correctness",severity:"suggestion",scope:"in_scope",file:"src/db.ts",line:88,summary:$s}')
  write_state "$STATE" "$(jq -nc --argjson f "$promoted" --arg s "$SQL" \
    '[{iteration:1,findings:[$f],addressed:[{file:"src/db.ts",line:88,summary:$s,
       promoted_from:"suggestion",promoted_by:"multi-persona",
       source_reviewers:["correctness","security"],promotion_reason:"multi_source"}]}]')"
  run check_exit "$(jq -nc --argjson b "$(blocker "src/db.ts" 88 "$SQL")" '{blockers:[$b]}')" "$STATE"
  [[ "$(status_of "$output")" == "NO_PROGRESS" ]]
}

@test "an unpromoted suggestion in history is not a blocker" {
  local sugg
  sugg=$(jq -nc --arg s "$SQL" \
    '{reviewer:"correctness",severity:"suggestion",scope:"in_scope",file:"src/db.ts",line:88,summary:$s}')
  write_state "$STATE" "$(jq -nc --argjson f "$sugg" '[{iteration:1,findings:[$f],addressed:[]}]')"
  run check_exit "$(jq -nc --argjson b "$(blocker "src/db.ts" 88 "$SQL")" '{blockers:[$b]}')" "$STATE"
  [[ "$(status_of "$output")" == "null" ]]
}

@test "a deferred out-of-scope blocker in history does not mask a repeated blocker" {
  # partition() defers every out_of_scope finding, so the loop never tried to
  # fix this one. Counting it makes history one larger than any current set.
  local a deferred
  a=$(blocker "src/db.ts" 88 "$SQL")
  deferred=$(blocker "src/parse.ts" 31 "$NULLDEREF" | jq -c '.scope = "out_of_scope"')
  write_state "$STATE" "$(jq -nc --argjson a "$a" --argjson d "$deferred" \
    '[{iteration:1,findings:[$a,$d]}]')"
  run check_exit "$(jq -nc --argjson a "$a" '{blockers:[$a]}')" "$STATE"
  [[ "$(status_of "$output")" == "NO_PROGRESS" ]]
}

@test "a blocker deferred last iteration is not a repeat when it becomes in-scope" {
  local b deferred
  b=$(blocker "src/parse.ts" 31 "$NULLDEREF")
  deferred=$(jq -c '.scope = "out_of_scope"' <<<"$b")
  write_state "$STATE" "$(jq -nc --argjson d "$deferred" '[{iteration:1,findings:[$d]}]')"
  run check_exit "$(jq -nc --argjson b "$b" '{blockers:[$b]}')" "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$(status_of "$output")" == "null" ]]
}

@test "empty history does not exit" {
  local b; b=$(blocker "src/db.ts" 88 "$SQL")
  write_state "$STATE" '[]'
  run check_exit "$(jq -nc --argjson b "$b" '{blockers:[$b]}')" "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$(status_of "$output")" == "null" ]]
}

@test "a still-failing check exits CI_STUCK on intersection, not equality" {
  # {build, lint} followed by {build} is a stuck build; equality would read
  # the departed lint as progress and keep looping.
  write_state "$STATE" '[{"iteration":1,"ci_status":"failure","ci_failed_checks":["build","lint"]}]'
  run check_exit '{"ci_failed_checks":["build"]}' "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$(status_of "$output")" == "CI_STUCK" ]]
  [[ "$output" == *"build"* ]]
}

@test "intervening skipped iterations do not clear a failing check" {
  # §4d.1 runs only when the panel has nothing left to flag, so iterations in
  # between record ci_status "skipped" and no names. Comparing against
  # history[-1] would intersect with nothing and never fire.
  write_state "$STATE" '[{"iteration":1,"ci_status":"failure","ci_failed_checks":["build"]},
                         {"iteration":2,"ci_status":"skipped"},
                         {"iteration":3,"ci_status":"skipped","ci_failed_checks":[]}]'
  run check_exit '{"ci_failed_checks":["build"]}' "$STATE"
  [[ "$(status_of "$output")" == "CI_STUCK" ]]
}

@test "names on a non-failure entry are ignored" {
  # §4i records ci_failed_checks only on a failure, so names riding on a
  # success entry are stale. Counting them fires CI_STUCK spuriously and, when
  # disjoint, hides the older real failure behind them.
  write_state "$STATE" '[{"iteration":1,"ci_status":"success","ci_failed_checks":["build"]}]'
  run check_exit '{"ci_failed_checks":["build"]}' "$STATE"
  [[ "$(status_of "$output")" == "null" ]]

  write_state "$STATE" '[{"iteration":1,"ci_status":"failure","ci_failed_checks":["build"]},
                         {"iteration":2,"ci_status":"success","ci_failed_checks":["docs"]}]'
  run check_exit '{"ci_failed_checks":["build"]}' "$STATE"
  [[ "$(status_of "$output")" == "CI_STUCK" ]]
}

@test "a blocker with no summary exits 2" {
  # summary is required by the finding contract; defaulting a missing key to ""
  # silently produced no match and bypassed NO_PROGRESS.
  write_state "$STATE" '[]'
  run bash -c "echo '{\"blockers\":[{\"severity\":\"blocker\",\"file\":\"a.ts\",\"line\":88}]}' |
    python3 '${SCRIPTS}/check_exit_conditions.py' --state '${STATE}'"
  [[ "$status" -eq 2 ]]
}

@test "disjoint check names do not exit" {
  write_state "$STATE" '[{"iteration":1,"ci_status":"failure","ci_failed_checks":["build"]}]'
  run check_exit '{"ci_failed_checks":["docs"]}' "$STATE"
  [[ "$(status_of "$output")" == "null" ]]
}

@test "malformed input exits 2" {
  write_state "$STATE" '[]'
  run bash -c "echo 'not json' | python3 '${SCRIPTS}/check_exit_conditions.py' --state '${STATE}'"
  [[ "$status" -eq 2 ]]
  [[ "$output" != *"Traceback"* ]]

  run bash -c "echo '[]' | python3 '${SCRIPTS}/check_exit_conditions.py' --state '${STATE}'"
  [[ "$status" -eq 2 ]]

  run bash -c "echo '{\"blockers\":\"x\"}' | python3 '${SCRIPTS}/check_exit_conditions.py' --state '${STATE}'"
  [[ "$status" -eq 2 ]]

  run bash -c "echo '{\"ci_failed_checks\":[1]}' | python3 '${SCRIPTS}/check_exit_conditions.py' --state '${STATE}'"
  [[ "$status" -eq 2 ]]

  run bash -c "echo '{}' | python3 '${SCRIPTS}/check_exit_conditions.py' --state '${BATS_TEST_TMPDIR}/missing.json'"
  [[ "$status" -eq 2 ]]
  [[ "$output" != *"Traceback"* ]]

  run bash -c "echo '{}' | python3 '${SCRIPTS}/check_exit_conditions.py'"
  [[ "$status" -ne 0 ]]
}

@test "a blocker with a non-string summary exits 2, not a traceback" {
  # tokens() calls .lower(); without a type check at the boundary this crashed
  # with an AttributeError and exit 1, breaking the documented 0/2 contract.
  write_state "$STATE" '[]'
  for bad in '123' '["x"]' '{}' 'null'; do
    run bash -c "echo '{\"blockers\":[{\"severity\":\"blocker\",\"summary\":${bad}}]}' |
      python3 '${SCRIPTS}/check_exit_conditions.py' --state '${STATE}'"
    [[ "$status" -eq 2 ]] || { echo "summary=${bad} gave status ${status}"; return 1; }
    [[ "$output" != *"Traceback"* ]]
  done

  run bash -c "echo '{\"blockers\":[{\"severity\":\"blocker\",\"file\":5,\"summary\":\"x\"}]}' |
    python3 '${SCRIPTS}/check_exit_conditions.py' --state '${STATE}'"
  [[ "$status" -eq 2 ]]
}

@test "a malformed finding in history is skipped, not fatal" {
  # state.json was written by a previous iteration, so junk there is not a
  # caller error to reject and must not crash the comparison.
  # Same file as the junk entry: is_match_or_summary short-circuits on a file
  # mismatch, so a differing file never reaches the summary normalization that
  # crashes.
  local b; b=$(blocker "src/db.ts" null "$SQL")
  write_state "$STATE" '[{"iteration":1,"findings":[{"severity":"blocker","file":"src/db.ts","summary":99}]}]'
  run check_exit "$(jq -nc --argjson b "$b" '{blockers:[$b]}')" "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *"Traceback"* ]]
  [[ "$(status_of "$output")" == "null" ]]
}

@test "the §4d comparison delegates to the shared matcher" {
  # Without this the §4d rule can drift from scripts/finding_matcher.py
  # independently, which is the failure mode issue #78 names.
  run python3 -c "
import sys
sys.path.insert(0, '${SCRIPTS}')
import check_exit_conditions, finding_matcher
if check_exit_conditions.is_match_or_summary is not finding_matcher.is_match_or_summary:
    print('check_exit_conditions must use the shared finding_matcher')
    sys.exit(1)
"
  [[ "$status" -eq 0 ]] || { echo "$output"; return 1; }
}
