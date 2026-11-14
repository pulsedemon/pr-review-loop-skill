#!/usr/bin/env bats

load test_helper

promote() {
  local stdin="$1"
  printf '%s\n' "$stdin" | python3 "${SCRIPTS}/promote_findings.py"
}

@test "fresh state keeps agreement endorsement and anchored solo suggestions nonblocking" {
  make_tmp_repo
  stub_cmd gh 'printf "%s\n" '\''{"number":42,"title":"Test","url":"https://github.com/o/r/pull/42","headRefName":"feat/x","baseRefName":"main","headRefOid":"abc"}'\'''
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  printf '%s\n' 'value = 1' > sample.py
  local input
  input=$(jq '{
    suggestion_promotion_threshold, adversary_promotion, adversary_solo_promotion,
    demoted: [],
    findings: [
      {reviewer:"correctness",severity:"suggestion",scope:"in_scope",file:"sample.py",line:1,
       summary:"agreement",detail:"optional clarity",source_reviewers:["correctness","tests"]},
      {reviewer:"correctness",severity:"suggestion",scope:"in_scope",file:"sample.py",line:1,
       summary:"endorsement",detail:"optional clarity",source_reviewers:["correctness","adversary"]},
      {reviewer:"adversary",severity:"suggestion",scope:"in_scope",file:"sample.py",line:1,
       summary:"solo",detail:"optional clarity",source_reviewers:["adversary"],
       finding_evidence:{file:"sample.py",line:1,symbol:"value"}}
    ]
  }' .git/pr-loop/state.json)
  run promote "$input"
  [[ "$status" -eq 0 ]]
  jq -e '
    .blockers == [] and .addressed == [] and .deferred == [] and
    [.suggestions[].summary] == ["agreement", "endorsement", "solo"] and
    .suggestions[2].finding_evidence.symbol == "value"
  ' <<<"$output"
}

@test "multi_source threshold met: suggestion promoted to blocker" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"missing null check","detail":"d",
      "source_reviewers":["correctness","security"]
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'"blockers"'* ]]
  [[ "$output" == *'multi_source'* ]]
  [[ "$output" == *'multi-persona'* ]]
}

@test "multi_source threshold not met: suggestion stays in suggestions[]" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"missing null check","detail":"d",
      "source_reviewers":["correctness"]
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'multi_source'* ]]
  [[ "$output" == *'"suggestions"'* ]]
}

@test "threshold=1 with one source still promotes (verifies >= not >)" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"s","detail":"d",
      "source_reviewers":["correctness"]
    }],
    "suggestion_promotion_threshold": 1,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'multi_source'* ]]
  [[ "$output" == *'"blockers"'* ]]
}

@test "threshold=1 with solo-adversary source routes through solo-adversary gate (not multi_source)" {
  # pin the §4d.0.5 invariant: a solo-adversary suggestion must always go
  # through the evidence-gated path so finding_evidence is verified and
  # demoted[] objection is honored. previously, threshold=1 silently routed
  # such findings through multi_source (distinct_count=1 >= 1), bypassing
  # verification entirely.
  make_tmp_repo
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/missing.ts","line":1,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 1,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]] || return 1
  [[ "$output" != *'multi_source'* ]] || return 1
  [[ "$output" == *'evidence_verification_failed'* ]] || return 1
}

@test "threshold=1 with two distinct sources still promotes via multi_source" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"s","detail":"d",
      "source_reviewers":["correctness","security"]
    }],
    "suggestion_promotion_threshold": 1,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]] || return 1
  [[ "$output" == *'multi_source'* ]] || return 1
}

@test "threshold=0 disables multi_source promotion" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"s","detail":"d",
      "source_reviewers":["correctness","security","tests"]
    }],
    "suggestion_promotion_threshold": 0,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'multi_source'* ]]
}

@test "out_of_scope finding goes to deferred as plain string" {
  local input='{
    "findings": [{
      "reviewer":"readability","severity":"suggestion","scope":"out_of_scope",
      "summary":"prefer guard clause","source_reviewers":["readability"]
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'"deferred"'* ]]
  [[ "$output" == *'prefer guard clause'* ]]
}

@test "deferred root-file location survives summary collection" {
  local input='{
    "findings": [{
      "reviewer":"readability","severity":"suggestion","scope":"out_of_scope",
      "file":"a.py","line":7,"summary":"optional readability","detail":"preference"
    }],
    "suggestion_promotion_threshold":0,"adversary_promotion":false,
    "adversary_solo_promotion":false,"demoted":[]
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  local rendered
  rendered=$(jq -r '.deferred[0]' <<<"$output")
  run python3 - "$REPO_ROOT" "$rendered" <<'PY'
import sys
sys.path.insert(0, sys.argv[1] + "/tools/recall-harness")
from collect_pr_corpus import SUMMARY_MARKER, parse_summary_bullets
anchored, unanchored = parse_summary_bullets(SUMMARY_MARKER + "\n- " + sys.argv[2])
assert anchored == [{"file": "a.py", "line": 7, "summary": "optional readability"}]
assert unanchored == []
PY
  [[ "$status" -eq 0 ]]
}

@test "in_scope blocker passes through to blockers[]" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"blocker","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"null deref","detail":"d",
      "source_reviewers":["correctness"]
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'"blockers"'* ]]
  [[ "$output" == *'null deref'* ]]
}

@test "in_scope nit passes through to nits[]" {
  local input='{
    "findings": [{
      "reviewer":"readability","severity":"nit","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"trailing whitespace","detail":"d",
      "source_reviewers":["readability"]
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'"nits"'* ]]
  [[ "$output" == *'trailing whitespace'* ]]
}

@test "multi-source nit stays a nit at the promotion threshold" {
  # The reason the tier exists. `suggestion` with two distinct sources promotes
  # to blocker at threshold 2; `nit` must not, however many personas raise it.
  # The other two nit tests are single-source, so they pass with the nit branch
  # moved below multi-source promotion -- verified by mutation, all 41 green --
  # which would silently reintroduce the escalation this tier prevents.
  local input='{
    "findings": [{
      "reviewer":"tests","severity":"nit","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"pass-through branch untested","detail":"d",
      "source_reviewers":["tests","yagni"]
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r '.nits | length' <<<"$output")" -eq 1 ]]
  [[ "$(jq -r '.blockers | length' <<<"$output")" -eq 0 ]]
  [[ "$(jq -r '.addressed | length' <<<"$output")" -eq 0 ]]
}

@test "malformed JSON exits 2" {
  run bash -c "echo 'not json' | python3 ${SCRIPTS}/promote_findings.py"
  [[ "$status" -eq 2 ]]
}

@test "missing required top-level field exits 2" {
  run bash -c "echo '{}' | python3 ${SCRIPTS}/promote_findings.py"
  [[ "$status" -eq 2 ]]
}

@test "adversary endorsement promotes regardless of threshold (threshold=99)" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"missing null check","detail":"d",
      "source_reviewers":["adversary","correctness"]
    }],
    "suggestion_promotion_threshold": 99,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'adversary_endorsed'* ]]
  [[ "$output" == *'"blockers"'* ]]
}

@test "adversary endorsement wins over multi-source when both would fire" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"missing null check","detail":"d",
      "source_reviewers":["adversary","correctness"]
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'adversary_endorsed'* ]]
  [[ "$output" != *'multi_source'* ]]
}

@test "adversary_promotion=false disables endorsement path; falls through to multi_source when threshold met" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"s","detail":"d",
      "source_reviewers":["adversary","correctness"]
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": false,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'adversary_endorsed'* ]]
  [[ "$output" == *'multi_source'* ]]
}

@test "malformed finding_evidence.file (non-string) defers instead of tracebacking" {
  # _verify_evidence is the trust boundary between LLM JSON and the script.
  # A non-string `file` would previously hit os.path.isabs(int) and crash;
  # now it routes to deferred[] with a typed shape reason.
  make_tmp_repo
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":42,"line":1,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]] || return 1
  [[ "$output" == *'evidence_verification_failed'* ]] || return 1
  [[ "$output" == *'file must be non-empty string'* ]] || return 1
  [[ "$output" != *'Traceback'* ]] || return 1
}

@test "adversary_promotion=false with threshold unmet leaves endorsement candidate in suggestions[]" {
  local input='{
    "findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"s","detail":"d",
      "source_reviewers":["adversary","correctness"]
    }],
    "suggestion_promotion_threshold": 99,
    "adversary_promotion": false,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'adversary_endorsed'* ]]
  [[ "$output" != *'multi_source'* ]]
  [[ "$output" == *'"suggestions"'* ]]
}

@test "solo-adversary suggestion with full evidence and no objection promotes" {
  make_tmp_repo
  mkdir -p src
  for i in $(seq 1 50); do echo "// line $i foo"; done > src/a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"adversary caught X","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":42,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]] || return 1
  [[ "$output" == *'evidence_gated_solo_adversary'* ]] || return 1
  # confirm the finding lands in blockers[], not deferred[]
  local block_count
  block_count=$(echo "$output" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["blockers"]))')
  [[ "$block_count" -eq 1 ]] || return 1
}

@test "solo-adversary gate fails when finding_evidence missing" {
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"]
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'evidence_gated_solo_adversary'* ]]
  [[ "$output" == *'"suggestions"'* ]]
}

@test "solo-adversary gate fails when severity is nit" {
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"nit","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":42,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'evidence_gated_solo_adversary'* ]]
  [[ "$output" == *'"nits"'* ]]
}

@test "solo-adversary gate fails when scope is out_of_scope" {
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"out_of_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":42,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'evidence_gated_solo_adversary'* ]]
  [[ "$output" == *'"deferred"'* ]]
}

@test "solo-adversary gate fails when panelist objected within 5 lines (same file)" {
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"adversary caught X","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":42,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": [{
      "file":"src/a.ts","line":40,"summary":"explicitly not a problem",
      "reviewer":"correctness","reason":"not_a_problem"
    }]
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'evidence_gated_solo_adversary'* ]]
  [[ "$output" == *'"suggestions"'* ]]
}

@test "solo-adversary gate passes when objection is in a different file" {
  make_tmp_repo
  mkdir -p src
  for i in $(seq 1 50); do echo "// line $i foo"; done > src/a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":42,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": [{
      "file":"src/b.ts","line":42,"summary":"different file",
      "reviewer":"correctness","reason":"not_a_problem"
    }]
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'evidence_gated_solo_adversary'* ]]
}

@test "solo-adversary gate passes when objection is more than 5 lines away" {
  make_tmp_repo
  mkdir -p src
  for i in $(seq 1 50); do echo "// line $i foo"; done > src/a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":42,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": [{
      "file":"src/a.ts","line":48,"summary":"not in window",
      "reviewer":"correctness","reason":"not_a_problem"
    }]
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'evidence_gated_solo_adversary'* ]]
}

@test "merge mode: adversary endorsement of one panel finding unions source_reviewers" {
  local input='{
    "panel_findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":40,"summary":"missing null check on user input","detail":"d",
      "source_reviewers":["correctness"]
    }],
    "adversary_findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"missing null check on user input here","detail":"d",
      "source_reviewers":["adversary"]
    }],
    "suggestion_promotion_threshold": 99,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'adversary_endorsed'* ]]
}

@test "merge mode: unmatched adversary finding stays solo (source_reviewers stays adversary)" {
  local input='{
    "panel_findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":40,"summary":"unrelated thing","detail":"d",
      "source_reviewers":["correctness"]
    }],
    "adversary_findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/b.ts","line":10,"summary":"different file finding","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/b.ts","line":10,"symbol":"x"}
    }],
    "suggestion_promotion_threshold": 99,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'adversary_endorsed'* ]]
}

@test "merge mode: line distance > 5 prevents match (matches match_findings.py rule)" {
  local input='{
    "panel_findings": [{
      "reviewer":"correctness","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":10,"summary":"missing null check","detail":"d",
      "source_reviewers":["correctness"]
    }],
    "adversary_findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"missing null check","detail":"d",
      "source_reviewers":["adversary"]
    }],
    "suggestion_promotion_threshold": 99,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'adversary_endorsed'* ]]
}

@test "merge mode: stdin with both findings and panel_findings exits 2" {
  local input='{
    "findings": [],
    "panel_findings": [],
    "adversary_findings": [],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 2 ]]
}

@test "merge mode: promote_findings delegates matching to shared matcher" {
  cat > "${BATS_TEST_TMPDIR}/cases.json" <<'JSON'
[
  {"a":{"file":"x.ts","line":10,"summary":"missing null check on user input"},"b":{"file":"x.ts","line":12,"summary":"missing null check on user input"},"expected":0},
  {"a":{"file":"x.ts","line":10,"summary":"missing null check on user input"},"b":{"file":"x.ts","line":16,"summary":"missing null check on user input"},"expected":1},
  {"a":{"file":"x.ts","line":10,"summary":"missing null check"},"b":{"file":"y.ts","line":10,"summary":"missing null check"},"expected":1},
  {"a":{"file":"x.ts","line":10,"summary":"foo bar baz"},"b":{"file":"x.ts","line":10,"summary":"completely unrelated stuff here"},"expected":1},
  {"a":{"file":"x.ts","line":10,"summary":"the and is"},"b":{"file":"x.ts","line":10,"summary":"of for at"},"expected":1},
  {"a":{"file":"x.ts","line":10,"summary":"missing null check"},"b":{"file":"x.ts","line":10,"summary":"the and is"},"expected":1}
]
JSON
  run python3 -c "
import json, sys
sys.path.insert(0, '${SCRIPTS}')
from promote_findings import _is_match
from finding_matcher import is_match
if _is_match is not is_match:
    print('promote_findings._is_match must be the shared finding_matcher.is_match')
    sys.exit(1)
cases = json.load(open('${BATS_TEST_TMPDIR}/cases.json'))
for c in cases:
    a, b, expected = c['a'], c['b'], c['expected']
    actual = 0 if _is_match(a, b) else 1
    if actual != expected:
        print(f'MISMATCH on {c}: _is_match={actual}, expected={expected}')
        sys.exit(1)
"
  [[ "$status" -eq 0 ]]
}

@test "evidence verification fails when file is missing" {
  make_tmp_repo
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/missing.ts","line":1,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run bash -c "echo '$input' | python3 ${SCRIPTS}/promote_findings.py"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'evidence_verification_failed'* ]]
  [[ "$output" == *'"deferred"'* ]]
}

@test "evidence verification fails when line exceeds file length" {
  make_tmp_repo
  printf 'one\ntwo\n' > a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"a.ts","line":1,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"a.ts","line":999,"symbol":"one"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run bash -c "echo '$input' | python3 ${SCRIPTS}/promote_findings.py"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'evidence_verification_failed'* ]]
}

@test "evidence verification fails when symbol is not in the file" {
  make_tmp_repo
  printf 'function foo() {}\n' > a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"a.ts","line":1,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"a.ts","line":1,"symbol":"bar"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run bash -c "echo '$input' | python3 ${SCRIPTS}/promote_findings.py"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'evidence_verification_failed'* ]]
}

@test "evidence verification fails when snippet is not in the file" {
  make_tmp_repo
  printf 'function foo() {}\n' > a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"a.ts","line":1,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"a.ts","line":1,"snippet":"function bar"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run bash -c "echo '$input' | python3 ${SCRIPTS}/promote_findings.py"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'evidence_verification_failed'* ]]
}

@test "evidence verification rejects line=1 on an empty file" {
  make_tmp_repo
  : > empty.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"empty.ts","line":1,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"empty.ts","line":1,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run bash -c "echo '$input' | python3 ${SCRIPTS}/promote_findings.py"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'evidence_verification_failed'* ]]
  [[ "$output" == *'out of bounds'* ]]
}

@test "evidence verification passes when symbol AND snippet both match" {
  make_tmp_repo
  printf 'function foo() { return 1; }\n' > a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"a.ts","line":1,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"a.ts","line":1,"symbol":"foo","snippet":"return 1"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run bash -c "echo '$input' | python3 ${SCRIPTS}/promote_findings.py"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'evidence_gated_solo_adversary'* ]]
  [[ "$output" == *'"blockers"'* ]]
}

@test "evidence verification rejects absolute path with 'path outside repo'" {
  make_tmp_repo
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"/etc/passwd","line":1,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"/etc/passwd","line":1,"symbol":"root"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]] || return 1
  [[ "$output" != *'evidence_gated_solo_adversary'* ]] || return 1
  [[ "$output" == *'path outside repo'* ]] || return 1
}

@test "evidence verification rejects parent-traversal path with 'path outside repo'" {
  make_tmp_repo
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"../escape.txt","line":1,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"../escape.txt","line":1,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]] || return 1
  [[ "$output" != *'evidence_gated_solo_adversary'* ]] || return 1
  [[ "$output" == *'path outside repo'* ]] || return 1
}

@test "evidence verification rejects oversize file with 'file too large'" {
  make_tmp_repo
  # write just past the 5MB cap (cap = 5*1024*1024 = 5242880)
  python3 -c 'open("big.txt","wb").write(b"x"*(5242881))'
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"big.txt","line":1,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"big.txt","line":1,"symbol":"x"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]] || return 1
  [[ "$output" != *'evidence_gated_solo_adversary'* ]] || return 1
  [[ "$output" == *'file too large to verify'* ]] || return 1
}

@test "adversary_solo_promotion=false leaves solo-adversary suggestion in suggestions[]" {
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":42,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": false,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *'evidence_gated_solo_adversary'* ]]
  [[ "$output" == *'"suggestions"'* ]]
}

@test "demoted[] with non-int line is treated as no objection (no traceback)" {
  make_tmp_repo
  mkdir -p src
  for i in $(seq 1 50); do echo "// line $i foo"; done > src/a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":42,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": [{
      "file":"src/a.ts","line":"40","summary":"string line",
      "reviewer":"correctness","reason":"not_a_problem"
    }]
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *"Traceback"* ]]
  [[ "$output" == *'evidence_gated_solo_adversary'* ]]
}

@test "demoted[] with null line is treated as no objection (no traceback)" {
  make_tmp_repo
  mkdir -p src
  for i in $(seq 1 50); do echo "// line $i foo"; done > src/a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":42,"symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": [{
      "file":"src/a.ts","line":null,"summary":"null line",
      "reviewer":"correctness","reason":"not_a_problem"
    }]
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *"Traceback"* ]]
  [[ "$output" == *'evidence_gated_solo_adversary'* ]]
}

@test "finding_evidence with non-int line routes to deferred with controlled reason" {
  make_tmp_repo
  mkdir -p src
  for i in $(seq 1 50); do echo "// line $i foo"; done > src/a.ts
  local input='{
    "findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"src/a.ts","line":42,"summary":"s","detail":"d",
      "source_reviewers":["adversary"],
      "finding_evidence":{"file":"src/a.ts","line":"42","symbol":"foo"}
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *"Traceback"* ]]
  [[ "$output" == *'evidence_verification_failed'* ]]
  [[ "$output" == *'line must be integer'* ]]
}

@test "merge mode: adversary blocker matched to a panel nit escalates to blockers[]" {
  local input='{
    "panel_findings": [{
      "reviewer":"tests","severity":"nit","scope":"in_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value","detail":"d",
      "source_reviewers":["tests"]
    }],
    "adversary_findings": [{
      "reviewer":"adversary","severity":"blocker","scope":"in_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value","detail":"d"
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r '.blockers | length' <<<"$output")" -eq 1 ]]
  [[ "$(jq -r '.nits | length' <<<"$output")" -eq 0 ]]
  [[ "$(jq -r '.blockers[0].source_reviewers | sort | join(",")' <<<"$output")" == "adversary,tests" ]]
  [[ "$(jq -r '.addressed | length' <<<"$output")" -eq 0 ]]
}

@test "merge mode: disabling promotion preserves a matched blocker and its diagnostics" {
  local severity input
  for severity in nit suggestion; do
    input=$(jq -n --arg severity "$severity" '{
    "panel_findings": [{
      "reviewer":"tests","severity":$severity,"scope":"in_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value",
      "detail":"optional clarity","suggested_fix":"rename the variable"
    }],
    "adversary_findings": [{
      "reviewer":"adversary","severity":"blocker","scope":"in_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value",
      "detail":"reachable null access","suggested_fix":"check the returned value",
      "finding_evidence":{"file":"a.py","line":10,"symbol":"parse"}
    }],
    "suggestion_promotion_threshold": 0,
    "adversary_promotion": false,
    "adversary_solo_promotion": false,
    "demoted": []
    }')
    run promote "$input"
    [[ "$status" -eq 0 ]]
    jq -e '
      .nits == [] and .suggestions == [] and .addressed == [] and
      (.blockers | length) == 1 and
      .blockers[0].reviewer == "adversary" and
      .blockers[0].detail == "reachable null access" and
      .blockers[0].suggested_fix == "check the returned value" and
      .blockers[0].finding_evidence == {file:"a.py",line:10,symbol:"parse"} and
      (.blockers[0].source_reviewers | sort) == ["adversary", "tests"]
    ' <<<"$output"
  done
}

@test "merge mode: adversary suggestion matched to a panel nit leaves the nit alone" {
  local input='{
    "panel_findings": [{
      "reviewer":"tests","severity":"nit","scope":"in_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value","detail":"d",
      "source_reviewers":["tests"]
    }],
    "adversary_findings": [{
      "reviewer":"adversary","severity":"suggestion","scope":"in_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value","detail":"d"
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r '.nits | length' <<<"$output")" -eq 1 ]]
  [[ "$(jq -r '.blockers | length' <<<"$output")" -eq 0 ]]
}

@test "merge mode: adversary blocker matched to an out_of_scope nit lands standalone" {
  # partition routes scope-first and _plain_deferred renders a bare string, so
  # escalating into the nit would swallow the blocker. the merge skips the
  # union instead: the blocker arrives standalone, the nit still defers.
  local input='{
    "panel_findings": [{
      "reviewer":"tests","severity":"nit","scope":"out_of_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value","detail":"d",
      "source_reviewers":["tests"]
    }],
    "adversary_findings": [{
      "reviewer":"adversary","severity":"blocker","scope":"in_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value","detail":"d"
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r '.blockers | length' <<<"$output")" -eq 1 ]]
  [[ "$(jq -r '.blockers[0].source_reviewers | join(",")' <<<"$output")" == "adversary" ]]
  [[ "$(jq -r '.deferred | length' <<<"$output")" -eq 1 ]]
}

@test "merge mode: out_of_scope adversary blocker never escalates a panel nit" {
  # the adversary's verdict includes its own deferral; escalating here would
  # mint an in_scope blocker from a finding the adversary itself deferred.
  # mutation-verified 2026-08-21: dropped the adv scope clause from
  # blocker_over_nit -> this failed (nit escalated, blockers 1).
  local input='{
    "panel_findings": [{
      "reviewer":"tests","severity":"nit","scope":"in_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value","detail":"d",
      "source_reviewers":["tests"]
    }],
    "adversary_findings": [{
      "reviewer":"adversary","severity":"blocker","scope":"out_of_scope",
      "file":"a.py","line":10,"summary":"unchecked json loads return value","detail":"d"
    }],
    "suggestion_promotion_threshold": 2,
    "adversary_promotion": true,
    "adversary_solo_promotion": true,
    "demoted": []
  }'
  run promote "$input"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r '.nits | length' <<<"$output")" -eq 1 ]]
  [[ "$(jq -r '.blockers | length' <<<"$output")" -eq 0 ]]
}
