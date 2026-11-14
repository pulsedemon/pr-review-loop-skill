#!/usr/bin/env bats

load test_helper

select_panel() {
  echo "$1" | python3 "${SCRIPTS}/select_panel.py"
}

PANEL='["correctness","tests","security","performance","readability","yagni","requirements","comments","error_handling","type_design","blind_spots"]'

@test "iteration 1 runs the full panel regardless of inputs" {
  local input out
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:1, delta_gate:true, delta_gate_min_candidates:4, prev_history:null, gate_results:[]}')
  out=$(select_panel "$input")
  [ "$(jq -r '.mode' <<<"$out")" = "full" ]
  [ "$(jq -r '.ran | length' <<<"$out")" -eq 11 ]
  [ "$(jq -r '.skipped | length' <<<"$out")" -eq 0 ]
}

@test "delta_gate=false runs the full panel on iteration 5" {
  local input out
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:5, delta_gate:false, delta_gate_min_candidates:4,
      prev_history:{findings:[]}, gate_results:[]}')
  out=$(select_panel "$input")
  [ "$(jq -r '.mode' <<<"$out")" = "full" ]
  [ "$(jq -r '.ran | length' <<<"$out")" -eq 11 ]
}

@test "non-JSON stdin exits 2" {
  run bash -c "echo 'nope' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "missing required key exits 2" {
  run bash -c "echo '{\"iteration\":1}' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "valid-JSON non-object stdin exits 2" {
  run bash -c "echo '[1,2]' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "empty panel exits 2" {
  local input
  input=$(jq -nc \
    '{panel:[], iteration:1, delta_gate:true, delta_gate_min_candidates:4,
      prev_history:null, gate_results:[]}')
  run bash -c "echo '$input' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "non-array panel exits 2" {
  local input
  input=$(jq -nc \
    '{panel:"correctness", iteration:1, delta_gate:true, delta_gate_min_candidates:4,
      prev_history:null, gate_results:[]}')
  run bash -c "echo '$input' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "panel with duplicate persona names exits 2" {
  local input
  input=$(jq -nc \
    '{panel:["correctness","tests","correctness"], iteration:1, delta_gate:true,
      delta_gate_min_candidates:4, prev_history:null, gate_results:[]}')
  run bash -c "echo '$input' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "panel with non-string entry exits 2" {
  local input
  input=$(jq -nc \
    '{panel:["correctness", {"name":"tests"}], iteration:1, delta_gate:true,
      delta_gate_min_candidates:4, prev_history:null, gate_results:[]}')
  run bash -c "echo '$input' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "non-integer iteration exits 2" {
  local input
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:"5", delta_gate:true, delta_gate_min_candidates:4,
      prev_history:null, gate_results:[]}')
  run bash -c "echo '$input' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "non-boolean delta_gate exits 2" {
  local input
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:5, delta_gate:"false", delta_gate_min_candidates:4,
      prev_history:{findings:[]}, gate_results:[]}')
  run bash -c "echo '$input' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "non-integer delta_gate_min_candidates exits 2" {
  local input
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:5, delta_gate:true, delta_gate_min_candidates:"4",
      prev_history:{findings:[]}, gate_results:[]}')
  run bash -c "echo '$input' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "boolean iteration exits 2 (bool is not an integer)" {
  # bool is an int subclass: a bare isinstance(_, int) check would accept
  # `true`/`false`. This guards the explicit bool-rejection clause.
  local input
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:true, delta_gate:true, delta_gate_min_candidates:4,
      prev_history:null, gate_results:[]}')
  run bash -c "echo '$input' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "boolean delta_gate_min_candidates exits 2 (bool is not an integer)" {
  # Same bool-as-int-subclass guard, for delta_gate_min_candidates.
  local input
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:5, delta_gate:true, delta_gate_min_candidates:false,
      prev_history:{findings:[]}, gate_results:[]}')
  run bash -c "echo '$input' | python3 '${SCRIPTS}/select_panel.py'"
  [ "$status" -eq 2 ]
}

@test "missing prev_history fails open to full panel on gated iterations" {
  local input out
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:3, delta_gate:true, delta_gate_min_candidates:4, gate_results:[]}')
  out=$(select_panel "$input")
  [ "$(jq -r '.mode' <<<"$out")" = "full" ]
  [ "$(jq -r '.ran | length' <<<"$out")" -eq 11 ]
  [ "$(jq -r '.skipped | length' <<<"$out")" -eq 0 ]
}

@test "non-dict prev_history fails open to full panel on gated iterations" {
  local input out
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:3, delta_gate:true, delta_gate_min_candidates:4,
      prev_history:"broken", gate_results:[]}')
  out=$(select_panel "$input")
  [ "$(jq -r '.mode' <<<"$out")" = "full" ]
  [ "$(jq -r '.ran | length' <<<"$out")" -eq 11 ]
  [ "$(jq -r '.skipped | length' <<<"$out")" -eq 0 ]
}

# A history entry whose findings include a blocker raised by `security`.
# Findings use the singular `reviewer` field — the shape templates/state.schema.json
# requires for a persisted history[].findings entry.
PREV_WITH_BLOCKER='{"findings":[
  {"reviewer":"security","severity":"blocker","scope":"in_scope","file":"a.py","line":1,"summary":"sql injection"},
  {"reviewer":"readability","severity":"suggestion","scope":"in_scope","file":"b.py","line":2,"summary":"rename"}
]}'

@test "open-blocker persona is always in ran, even with no gate result" {
  local input out
  input=$(jq -nc --argjson p "$PANEL" --argjson h "$PREV_WITH_BLOCKER" \
    '{panel:$p, iteration:3, delta_gate:true, delta_gate_min_candidates:4,
      prev_history:$h, gate_results:[]}')
  out=$(select_panel "$input")
  jq -e '.ran | index("security")' <<<"$out"
  jq -e '.open_blocker_carryover | index("security")' <<<"$out"
  [ "$(jq -r '.gate_fail_open | length' <<<"$out")" -eq 10 ]
}

@test "open-blocker carryover reads source_reviewers on a promoted/merged finding" {
  # A finding promoted via adversary/multi-source merge carries source_reviewers
  # instead of (or alongside) a singular reviewer. Carryover must honor it too.
  local prev input out
  prev='{"findings":[
    {"severity":"blocker","scope":"in_scope","file":"a.py","line":1,"summary":"promoted",
     "source_reviewers":["error_handling","adversary"]}
  ]}'
  input=$(jq -nc --argjson p "$PANEL" --argjson h "$prev" \
    '{panel:$p, iteration:3, delta_gate:true, delta_gate_min_candidates:99,
      prev_history:$h, gate_results:[]}')
  out=$(select_panel "$input")
  # error_handling is a panel persona and must carry over; adversary is not in
  # the panel, so it is correctly absent from the carryover.
  jq -e '.open_blocker_carryover | index("error_handling")' <<<"$out"
  [ "$(jq -r '.open_blocker_carryover | index("adversary")' <<<"$out")" = "null" ]
}

@test "a suggestion does NOT make its persona open-blocker" {
  local input out
  input=$(jq -nc --argjson p "$PANEL" --argjson h "$PREV_WITH_BLOCKER" \
    '{panel:$p, iteration:3, delta_gate:true, delta_gate_min_candidates:99,
      prev_history:$h, gate_results:[]}')
  out=$(select_panel "$input")
  # min_candidates 99 forces the gate to be skipped; below the cap every
  # candidate runs. The assertion checks open_blocker_carryover, not ran:
  # readability raised only a suggestion, so it must not be carried over.
  [ "$(jq -r '.open_blocker_carryover | index("readability")' <<<"$out")" = "null" ]
}

@test "below the candidate cap, all candidates run without a gate" {
  # No prior blockers => 11 candidates, but cap is 99, so the gate is skipped
  # and every candidate runs => full panel.
  local input out
  input=$(jq -nc --argjson p "$PANEL" \
    '{panel:$p, iteration:4, delta_gate:true, delta_gate_min_candidates:99,
      prev_history:{findings:[]}, gate_results:[]}')
  out=$(select_panel "$input")
  [ "$(jq -r '.mode' <<<"$out")" = "full" ]
  [ "$(jq -r '.ran | length' <<<"$out")" -eq 11 ]
}

@test "at or above the cap, gate relevant=true runs and relevant=false skips" {
  # 11 candidates, cap 4 => gate is consulted. Mark two relevant, the rest
  # not. All 11 have a result, so no fail-open.
  local gate input out
  gate=$(jq -nc '[
    {reviewer:"correctness",relevant:true,reason:"logic touched"},
    {reviewer:"tests",relevant:true,reason:"new test file"},
    {reviewer:"security",relevant:false,reason:"docs delta"},
    {reviewer:"performance",relevant:false,reason:"docs delta"},
    {reviewer:"readability",relevant:false,reason:"docs delta"},
    {reviewer:"yagni",relevant:false,reason:"docs delta"},
    {reviewer:"requirements",relevant:false,reason:"docs delta"},
    {reviewer:"comments",relevant:false,reason:"docs delta"},
    {reviewer:"error_handling",relevant:false,reason:"docs delta"},
    {reviewer:"type_design",relevant:false,reason:"docs delta"},
    {reviewer:"blind_spots",relevant:false,reason:"docs delta"}]')
  input=$(jq -nc --argjson p "$PANEL" --argjson g "$gate" \
    '{panel:$p, iteration:4, delta_gate:true, delta_gate_min_candidates:4,
      prev_history:{findings:[]}, gate_results:$g}')
  out=$(select_panel "$input")
  [ "$(jq -r '.mode' <<<"$out")" = "delta_gated" ]
  [ "$(jq -rc '.ran | sort' <<<"$out")" = '["correctness","tests"]' ]
  [ "$(jq -r '.gate_relevant | sort | join(",")' <<<"$out")" = "correctness,tests" ]
  [ "$(jq -r '.gate_fail_open | length' <<<"$out")" -eq 0 ]
}

@test "a candidate with no gate result fails open into ran and gate_fail_open" {
  # Cap 4, 11 candidates, but only one gate result provided => the other 10
  # fail open.
  local gate input out
  gate=$(jq -nc '[{reviewer:"correctness",relevant:false,reason:"docs delta"}]')
  input=$(jq -nc --argjson p "$PANEL" --argjson g "$gate" \
    '{panel:$p, iteration:4, delta_gate:true, delta_gate_min_candidates:4,
      prev_history:{findings:[]}, gate_results:$g}')
  out=$(select_panel "$input")
  # correctness skipped (relevant:false); the other 10 fail open.
  [ "$(jq -r '.ran | length' <<<"$out")" -eq 10 ]
  [ "$(jq -r '.gate_fail_open | length' <<<"$out")" -eq 10 ]
  [ "$(jq -r '.ran | index("correctness")' <<<"$out")" = "null" ]
}

@test "open-blocker personas skip the gate even when a result marks them irrelevant" {
  local gate input out
  gate=$(jq -nc '[{reviewer:"security",relevant:false,reason:"stale"}]')
  input=$(jq -nc --argjson p "$PANEL" --argjson h "$PREV_WITH_BLOCKER" --argjson g "$gate" \
    '{panel:$p, iteration:3, delta_gate:true, delta_gate_min_candidates:4,
      prev_history:$h, gate_results:$g}')
  out=$(select_panel "$input")
  # security raised a blocker last iteration; it runs regardless of the
  # (stale) gate result, and is NOT listed under gate_relevant.
  jq -e '.ran | index("security")' <<<"$out"
  [ "$(jq -r '.gate_relevant | index("security")' <<<"$out")" = "null" ]
}

@test "a gate result for a non-panel reviewer is ignored" {
  local gate input out
  gate=$(jq -nc '[
    {reviewer:"ghost",relevant:true,reason:"not a real persona"},
    {reviewer:"correctness",relevant:true,reason:"logic touched"},
    {reviewer:"tests",relevant:false,reason:"x"},
    {reviewer:"security",relevant:false,reason:"x"},
    {reviewer:"performance",relevant:false,reason:"x"},
    {reviewer:"readability",relevant:false,reason:"x"},
    {reviewer:"yagni",relevant:false,reason:"x"},
    {reviewer:"requirements",relevant:false,reason:"x"},
    {reviewer:"comments",relevant:false,reason:"x"},
    {reviewer:"error_handling",relevant:false,reason:"x"},
    {reviewer:"type_design",relevant:false,reason:"x"},
    {reviewer:"blind_spots",relevant:false,reason:"x"}]')
  input=$(jq -nc --argjson p "$PANEL" --argjson g "$gate" \
    '{panel:$p, iteration:4, delta_gate:true, delta_gate_min_candidates:4,
      prev_history:{findings:[]}, gate_results:$g}')
  out=$(select_panel "$input")
  # "ghost" is not in the panel, so it never appears in any output array.
  [ "$(jq -r '.ran | index("ghost")' <<<"$out")" = "null" ]
  [ "$(jq -rc '.ran | sort' <<<"$out")" = '["correctness"]' ]
}
