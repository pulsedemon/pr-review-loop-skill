#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
  mkdir -p .git/pr-loop
}

@test "review incomplete records a completed non-success run" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"status":"running","history":[]}
EOF
  TERMINAL_STATUS=REVIEW_INCOMPLETE run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 0 ]]
  jq -e '.status == "review_incomplete" and (.completed_at | type == "string")' .git/pr-loop/state.json
  jq -e '.terminal_status == "REVIEW_INCOMPLETE"' .git/pr-loop/metrics.jsonl
  jq -e '.properties.status.enum | index("review_incomplete") != null' "${REPO_ROOT}/templates/state.schema.json"
}

@test "write_terminal_metric emits expected rollup shape" {
  cat > .git/pr-loop/state.json <<'EOF'
{
  "owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":2,
  "loop_started_at":"2026-05-16T12:00:00Z",
  "history":[
    {"findings":[{"severity":"blocker","scope":"in_scope","summary":"s","file":"a","line":1,"detail":"d"}],"addressed":[],"deferred":[]},
    {"findings":[{"severity":"suggestion","scope":"in_scope","summary":"s2","file":"b","line":2,"detail":"d"}],"addressed":[],"deferred":[]}
  ]
}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 0 ]]

  local line
  line=$(tail -1 .git/pr-loop/metrics.jsonl)
  [[ "$(jq -r .kind                 <<<"$line")" == "terminal" ]]
  [[ "$(jq -r .terminal_status      <<<"$line")" == "SUCCESS" ]]
  [[ "$(jq -r .iterations_completed <<<"$line")" == "2" ]]
  [[ "$(jq -r .totals.blockers      <<<"$line")" == "1" ]]
  [[ "$(jq -r .totals.suggestions   <<<"$line")" == "1" ]]
  [[ "$(jq -r .pr                   <<<"$line")" == "o/r#9" ]]
  # wall_clock_seconds must be a non-negative int when loop_started_at is set
  local wall
  wall=$(jq -r .wall_clock_seconds <<<"$line")
  [[ "$wall" -ge 0 ]]
}

@test "write_terminal_metric marks state.json completed with the lowercase terminal status" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":1,"status":"running","history":[]}
EOF
  TERMINAL_STATUS=NO_PROGRESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r .status .git/pr-loop/state.json)" == "no_progress" ]]
  [[ "$(jq -r .completed_at .git/pr-loop/state.json)" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]]
  [[ "$(jq -r .iteration .git/pr-loop/state.json)" == "1" ]]
}

@test "write_terminal_metric rejects a misspelled status before marking state" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":1,"status":"running","history":[]}
EOF
  TERMINAL_STATUS=SUCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"terminal status must be one of"* ]]
  [[ "$(jq -r .status .git/pr-loop/state.json)" == "running" ]]
  [[ -z "$(jq -r '.completed_at // empty' .git/pr-loop/state.json)" ]]
  [[ ! -f .git/pr-loop/metrics.jsonl ]]
}

@test "write_terminal_metric marks state.json completed even when the metric append fails" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":1,"status":"running","history":[]}
EOF
  mkdir .git/pr-loop/metrics.jsonl
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -ne 0 ]]
  [[ "$(jq -r .status .git/pr-loop/state.json)" == "success" ]]
  [[ -n "$(jq -r '.completed_at // empty' .git/pr-loop/state.json)" ]]
  # the temp file is created beside state.json so the rename is atomic; none may leak
  [[ -z "$(ls .git/pr-loop/state.json.tmp.* 2>/dev/null)" ]]
}

@test "write_terminal_metric emits wall -1 when loop_started_at missing" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"history":[]}
EOF
  TERMINAL_STATUS=SETUP_ERROR run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r .wall_clock_seconds < <(tail -1 .git/pr-loop/metrics.jsonl))" == "-1" ]]
}

@test "write_terminal_metric writes iterations_completed=0 when .iteration missing" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"history":[]}
EOF
  TERMINAL_STATUS=SETUP_ERROR run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r .iterations_completed < <(tail -1 .git/pr-loop/metrics.jsonl))" == "0" ]]
}

@test "write_terminal_metric exits 2 when TERMINAL_STATUS missing" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"history":[]}
EOF
  run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"TERMINAL_STATUS"* ]]
}

@test "write_terminal_metric exits 2 when .iteration is a JSON string" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":"2","history":[]}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *".iteration must be a non-negative integer"* ]]
}

@test "write_terminal_metric exits 2 when .iteration is a float" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":1.5,"history":[]}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *".iteration must be a non-negative integer"* ]]
}

@test "write_terminal_metric exits 2 when .iteration is a bool" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":true,"history":[]}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *".iteration must be a non-negative integer"* ]]
}

@test "write_terminal_metric treats explicit nulls like jq defaults" {
  cat > .git/pr-loop/state.json <<'EOF'
{
  "owner":"o",
  "repo":"r",
  "pr_number":9,
  "max_iterations":15,
  "iteration":0,
  "approvers_required":null,
  "pr_scope_mode":null,
  "max_new_loc":null,
  "suggestion_promotion_threshold":null,
  "adversary_promotion":null,
  "adversary_solo_promotion":null,
  "adversary_panel_visibility":null,
  "approvers_required_list":null,
  "history":[]
}
EOF
  TERMINAL_STATUS=SETUP_ERROR run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 0 ]]

  local line
  line=$(tail -1 .git/pr-loop/metrics.jsonl)
  [[ "$(jq -r .panel_size <<<"$line")" == "0" ]]
  [[ "$(jq -r .knobs.approvers_required <<<"$line")" == "all" ]]
  [[ "$(jq -r .knobs.pr_scope <<<"$line")" == "auto" ]]
  [[ "$(jq -r .knobs.max_new_loc <<<"$line")" == "1000" ]]
  [[ "$(jq -r .knobs.suggestion_promotion_threshold <<<"$line")" == "2" ]]
  [[ "$(jq -r .knobs.adversary_promotion <<<"$line")" == "true" ]]
  [[ "$(jq -r .knobs.adversary_solo_promotion <<<"$line")" == "true" ]]
  [[ "$(jq -r .knobs.adversary_panel_visibility <<<"$line")" == "full" ]]
}

@test "write_terminal_metric exits 2 on malformed state json" {
  printf '{broken\n' > .git/pr-loop/state.json
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_terminal_metric: failed to parse state.json"* ]]
}

@test "write_terminal_metric exits 2 on invalid utf-8 state json" {
  python3 - <<'PY'
from pathlib import Path
Path(".git/pr-loop/state.json").write_bytes(b'{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"history":[],"bad":"\xff"}')
PY
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_terminal_metric: failed to parse state.json"* ]]
}

@test "write_terminal_metric preserves false boolean knobs" {
  cat > .git/pr-loop/state.json <<'EOF'
{
  "owner":"o",
  "repo":"r",
  "pr_number":9,
  "max_iterations":15,
  "iteration":0,
  "adversary_promotion":false,
  "adversary_solo_promotion":false,
  "history":[]
}
EOF
  TERMINAL_STATUS=SETUP_ERROR run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 0 ]]

  local line
  line=$(tail -1 .git/pr-loop/metrics.jsonl)
  [[ "$(jq -r .knobs.adversary_promotion <<<"$line")" == "false" ]]
  [[ "$(jq -r .knobs.adversary_solo_promotion <<<"$line")" == "false" ]]
}

@test "write_terminal_metric exits 2 when required pr identity is missing" {
  cat > .git/pr-loop/state.json <<'EOF'
{"repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"history":[]}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_terminal_metric: state.json missing required field 'owner'"* ]]
}

@test "write_terminal_metric exits 2 on invalid loop_started_at" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"loop_started_at":"not-a-date","history":[]}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_terminal_metric: loop_started_at must be an ISO 8601 timestamp"* ]]
}

@test "write_terminal_metric exits 2 on timezone-less loop_started_at" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"loop_started_at":"2026-05-20T02:04:14","history":[]}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_terminal_metric: loop_started_at must include a timezone offset or Z suffix"* ]]
}

@test "write_terminal_metric exits 2 on wrong nested state types" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"history":{}}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_terminal_metric: state.json field 'history' must be a present list"* ]]
}

@test "write_terminal_metric exits 2 when history is missing" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_terminal_metric: state.json field 'history' must be a present list"* ]]
}

@test "write_terminal_metric exits 2 on bad approvers_required_list type" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"approvers_required_list":{},"history":[]}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_terminal_metric: state.json field 'approvers_required_list' must be a list"* ]]
}

@test "write_terminal_metric exits 2 when loop_started_at is non-string" {
  cat > .git/pr-loop/state.json <<'EOF'
{"owner":"o","repo":"r","pr_number":9,"max_iterations":15,"iteration":0,"loop_started_at":123,"history":[]}
EOF
  TERMINAL_STATUS=SUCCESS run bash "${SCRIPTS}/write_terminal_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_terminal_metric: loop_started_at must be a string when present"* ]]
}
