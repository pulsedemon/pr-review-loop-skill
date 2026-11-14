#!/usr/bin/env bats

# In a linked worktree `.git` is a file, so loop state lives under
# `git rev-parse --git-dir`, not `.git/pr-loop`. Shipped instructions must say
# `<git-dir>/pr-loop`; fixtures under tests/ use `.git/pr-loop` on purpose.

load test_helper

@test "shipped docs never hard-code .git/pr-loop" {
  cd "$REPO_ROOT"
  run grep -rnF '.git/pr-loop' \
    SKILL.md AGENTS.md README.md CLAUDE.md docs/*.md \
    reviewers gates templates ci-integrations hosts \
    tools/recall-harness/README.md
  [[ "$status" -eq 1 ]] || {
    echo "use <git-dir>/pr-loop or \"\$(git rev-parse --git-dir)/pr-loop\" instead:"
    echo "$output"
    return 1
  }
}

@test "state lives under the worktree's git dir and check_exit_conditions reads it" {
  make_tmp_repo
  local main_checkout="$PWD"
  git worktree add -q -b feature "${BATS_TEST_TMPDIR}/wt"
  cd "${BATS_TEST_TMPDIR}/wt"
  stub_cmd gh 'cat <<JSON
{"number":42,"title":"Test","url":"https://github.com/o/r/pull/42","headRefName":"feature","baseRefName":"main","headRefOid":"deadbeef","body":"","isDraft":false}
JSON'
  run bash "${SCRIPTS}/state_init.sh" o r 42
  [[ "$status" -eq 0 ]]
  local state
  state="$(git rev-parse --git-dir)/pr-loop/state.json"
  [[ -f "$state" ]]
  [[ ! -e "${main_checkout}/.git/pr-loop/state.json" ]]
  run bash -c 'echo "{\"phase\":\"entry\"}" | python3 "$1" --state "$2"' _ \
    "${SCRIPTS}/check_exit_conditions.py" "$state"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *'"terminal_status": null'* ]]
}
