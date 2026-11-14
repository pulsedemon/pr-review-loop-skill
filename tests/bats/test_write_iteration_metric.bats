#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
  mkdir -p .git/pr-loop
}

write_state() {
  cat > .git/pr-loop/state.json <<EOF
$1
EOF
}

@test "write_iteration_metric emits one line with expected shape" {
  write_state '{
    "iteration": 2,
    "shallow_adversary_runs": 0,
    "history": [{
      "ci_status": "skipped",
      "findings": [
        {"severity":"blocker","scope":"in_scope","summary":"s","file":"a","line":1,"detail":"d"},
        {"severity":"suggestion","scope":"in_scope","summary":"s2","file":"b","line":2,"detail":"d"}
      ],
      "addressed": [
        {"promotion_reason":"multi_source"}
      ],
      "deferred": []
    }]
  }'
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 0 ]]

  local line
  line=$(cat .git/pr-loop/metrics.jsonl)
  [[ "$(jq -r .kind         <<<"$line")" == "iteration" ]]
  [[ "$(jq -r .iteration    <<<"$line")" == "2" ]]
  [[ "$(jq -r .pr           <<<"$line")" == "o/r#9" ]]
  [[ "$(jq -r .ci_status    <<<"$line")" == "skipped" ]]
  [[ "$(jq -r .n_blockers    <<<"$line")" == "1" ]]
  [[ "$(jq -r .n_suggestions <<<"$line")" == "1" ]]
  [[ "$(jq -r .promoted.multi_source <<<"$line")" == "1" ]]
  [[ "$(jq -rc .models <<<"$line")" == "{}" ]]
}

@test "write_iteration_metric folds model_routing into a models map" {
  write_state '{
    "iteration": 2,
    "history": [{
      "ci_status": "skipped",
      "findings": [],
      "addressed": [],
      "deferred": [],
      "model_routing": {
        "delta_gate": {"tier":"cheap","model":"haiku"},
        "reviewer": {"tier":"standard","model":"sonnet"},
        "adversary": {"tier":"inherit"}
      }
    }]
  }'
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 0 ]]

  local line
  line=$(cat .git/pr-loop/metrics.jsonl)
  [[ "$(jq -r .models.delta_gate <<<"$line")" == "haiku" ]]
  [[ "$(jq -r .models.reviewer   <<<"$line")" == "sonnet" ]]
  [[ "$(jq -r .models.adversary  <<<"$line")" == "inherit" ]]
}

@test "write_iteration_metric exits 2 when env missing" {
  write_state '{"iteration":0,"history":[{}]}'
  run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"OWNER/REPO/PR_NUMBER"* ]]
}

@test "write_iteration_metric exits 2 when state missing" {
  rm -f .git/pr-loop/state.json
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"state file missing"* ]]
}

@test "write_iteration_metric exits 2 when PR_NUMBER non-numeric" {
  write_state '{"iteration":0,"history":[{}]}'
  OWNER=o REPO=r PR_NUMBER=foo run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"PR_NUMBER must be numeric"* ]]
}

@test "write_iteration_metric exits 2 when .iteration is a JSON string" {
  write_state '{"iteration":"2","history":[{"findings":[],"addressed":[],"deferred":[]}]}'
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *".iteration must be a non-negative integer"* ]]
}

@test "write_iteration_metric exits 2 when .iteration is a float" {
  write_state '{"iteration":1.5,"history":[{"findings":[],"addressed":[],"deferred":[]}]}'
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *".iteration must be a non-negative integer"* ]]
}

@test "write_iteration_metric exits 2 when .iteration is a bool" {
  write_state '{"iteration":true,"history":[{"findings":[],"addressed":[],"deferred":[]}]}'
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *".iteration must be a non-negative integer"* ]]
}

@test "write_iteration_metric treats explicit nulls like jq defaults" {
  write_state '{
    "iteration": 2,
    "shallow_adversary_runs": null,
    "history": [{
      "ci_status": null,
      "findings": [],
      "addressed": [],
      "deferred": []
    }]
  }'
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 0 ]]

  local line
  line=$(cat .git/pr-loop/metrics.jsonl)
  [[ "$(jq -r .ci_status <<<"$line")" == "skipped" ]]
  [[ "$(jq -r .shallow_adversary_runs <<<"$line")" == "0" ]]
}

@test "write_iteration_metric exits 2 on malformed state json" {
  printf '{broken\n' > .git/pr-loop/state.json
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_iteration_metric: failed to parse state.json"* ]]
}

@test "write_iteration_metric exits 2 on invalid utf-8 state json" {
  python3 - <<'PY'
from pathlib import Path
Path(".git/pr-loop/state.json").write_bytes(b'{"iteration":0,"history":[],"bad":"\xff"}')
PY
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_iteration_metric: failed to parse state.json"* ]]
}

@test "write_iteration_metric exits 2 on wrong nested state types" {
  write_state '{
    "iteration": 2,
    "history": [{
      "ci_status": "skipped",
      "findings": {},
      "addressed": [],
      "deferred": []
    }]
  }'
  OWNER=o REPO=r PR_NUMBER=9 run bash "${SCRIPTS}/write_iteration_metric.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"write_iteration_metric: history[-1] field 'findings' must be a list"* ]]
}
