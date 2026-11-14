#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
}

prepare_resume() {
  git remote add origin https://github.com/owner/repo.git
  git branch -m feature
  export FETCH_TEST_GIT
  FETCH_TEST_GIT=$(command -v git)
  export FETCH_TEST_REMOTE
  FETCH_TEST_REMOTE=$(git rev-parse HEAD)
  export FETCH_TEST_ACTIONS="${BATS_TEST_TMPDIR}/actions"
  mkdir -p .git/pr-loop
  jq -n --arg head "$FETCH_TEST_REMOTE" '{
    owner: "owner", repo: "repo", pr_number: 1, head_branch: "feature", initial_head_sha: $head,
    iteration: 0, max_iterations: 2, history: []
  }' >.git/pr-loop/state.json
  stub_cmd gh '
    case "$*" in
      --version) echo "gh version 2.50.0" ;;
      "pr view "*)
        if [[ "${FETCH_TEST_MOVE_REMOTE:-}" == true ]]; then
          echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa > .git/moved-remote
        fi
        printf "feature\tmain\n" ;;
      "pr checkout "*) echo checkout >> "$FETCH_TEST_ACTIONS" ;;
      *) exit 1 ;;
    esac'
  stub_cmd git '
    case "$1" in
      fetch)
        if [[ "${FETCH_TEST_FETCH_FAIL:-}" == true ]]; then exit 1; fi
        if [[ -f .git/moved-remote ]]; then
          cp .git/moved-remote .git/FETCH_HEAD
        else
          printf "%s\n" "$FETCH_TEST_REMOTE" > .git/FETCH_HEAD
        fi ;;
      pull) echo pull >> "$FETCH_TEST_ACTIONS" ;;
      *) exec "$FETCH_TEST_GIT" "$@" ;;
    esac'
}

@test "exits 7 when gh CLI missing" {
  # Build a minimal PATH lacking gh; PATH= on the run invocation is what
  # actually constrains the subshell, the trim was a no-op.
  local p
  p="${BATS_TEST_TMPDIR}/empty-path"
  mkdir -p "$p"
  ln -sf /bin/bash "$p/bash"
  ln -sf /usr/bin/git "$p/git"
  PATH="$p" run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 7 ]]
  [[ "$output" == *"gh CLI"* ]]
}

@test "exits 2 on usage error" {
  run bash "${SCRIPTS}/fetch_pr.sh"
  [[ "$status" -eq 2 ]]
}

@test "exits 7 when gh version is too old" {
  stub_cmd gh 'echo "gh version 2.49.2 (2024-05-01)"; exit 0'
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 7 ]]
  [[ "$output" == *"older than required"* ]]
  [[ "$output" == *"2.50.0"* ]]
}

@test "exits 5 on origin mismatch" {
  stub_cmd gh 'echo "gh version 2.50.0 (2024-01-01)"; exit 0'
  git remote add origin https://github.com/other/repo.git
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 5 ]]
  [[ "$output" == *"does not match"* ]]
}

@test "exits 5 when origin is a prefixed sibling repo (no substring false-accept)" {
  stub_cmd gh 'echo "gh version 2.50.0 (2024-01-01)"; exit 0'
  git remote add origin https://github.com/owner/repo-internal.git
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 5 ]]
  [[ "$output" == *"does not match"* ]]
}

@test "accepts gh 2.50.0 and resumes a matching recorded head without checkout or pull" {
  prepare_resume
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 0 ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "preserves the recorded head when remote moves after validation" {
  prepare_resume
  export FETCH_TEST_MOVE_REMOTE=true
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 0 ]]
  [[ -f .git/moved-remote ]]
  [[ "$(git rev-parse HEAD)" == "$FETCH_TEST_REMOTE" ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "refuses a different current branch on unfinished resume" {
  prepare_resume
  git branch -m elsewhere
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 12 ]]
  [[ "$(git rev-parse --abbrev-ref HEAD)" == elsewhere ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "rejects an unrecorded local commit before checkout" {
  prepare_resume
  git commit -q --allow-empty -m "local change"
  local head_before
  head_before=$(git rev-parse HEAD)
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 12 ]]
  [[ "$output" == *EXTERNAL_PUSH* ]]
  [[ "$(git rev-parse HEAD)" == "$head_before" ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "rejects remote movement before fast-forwarding" {
  prepare_resume
  FETCH_TEST_REMOTE=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 12 ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "rejects a failed remote fetch before checkout" {
  prepare_resume
  export FETCH_TEST_FETCH_FAIL=true
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 12 ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "routes dirty unfinished state to external push" {
  prepare_resume
  touch untracked.txt
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 12 ]]
  [[ "$output" == *EXTERNAL_PUSH* ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "preserves setup refusal for a dirty fresh run" {
  prepare_resume
  rm .git/pr-loop/state.json
  touch untracked.txt
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 6 ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "does not resume completed same-pr state" {
  prepare_resume
  jq '.completed_at = "2026-09-10T00:00:00Z" | .initial_head_sha = "old"' \
    .git/pr-loop/state.json >"${BATS_TEST_TMPDIR}/updated.json"
  cp "${BATS_TEST_TMPDIR}/updated.json" .git/pr-loop/state.json
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 0 ]]
  [[ -e "$FETCH_TEST_ACTIONS" ]]
}

@test "refuses a different pr before checkout" {
  prepare_resume
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 2
  [[ "$status" -eq 8 ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "refuses malformed state before checkout" {
  prepare_resume
  echo '{broken' >.git/pr-loop/state.json
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 8 ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "refuses inconsistent history before checkout" {
  prepare_resume
  jq '.iteration = 1' .git/pr-loop/state.json >"${BATS_TEST_TMPDIR}/updated.json"
  cp "${BATS_TEST_TMPDIR}/updated.json" .git/pr-loop/state.json
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 8 ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "routes exhausted resume to max iterations before checkout" {
  prepare_resume
  jq '.iteration = 2 | .history = [
    {iteration: 1, head_sha_after: .initial_head_sha},
    {iteration: 2, head_sha_after: .initial_head_sha}
  ]' .git/pr-loop/state.json >"${BATS_TEST_TMPDIR}/updated.json"
  cp "${BATS_TEST_TMPDIR}/updated.json" .git/pr-loop/state.json
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 13 ]]
  [[ "$output" == *MAX_ITERATIONS* ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}

@test "re-emits scope abort before checkout" {
  prepare_resume
  jq '.pr_scope = {user_decision: "abort"}' \
    .git/pr-loop/state.json >"${BATS_TEST_TMPDIR}/updated.json"
  cp "${BATS_TEST_TMPDIR}/updated.json" .git/pr-loop/state.json
  run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
  [[ "$status" -eq 14 ]]
  [[ "$output" == *SCOPE_SPLIT_RECOMMENDED* ]]
  [[ ! -e "$FETCH_TEST_ACTIONS" ]]
}


@test "invalid completion markers cannot bypass resume checks" {
  prepare_resume
  for marker in '0' '{}' 'true' 'null' '"invalid"' '"2026-09-10T00:00:00"' '"2026-09-10X00:00+00:00"'; do
    jq --argjson marker "$marker" '.completed_at = $marker' .git/pr-loop/state.json > .git/pr-loop/edited.json
    mv .git/pr-loop/edited.json .git/pr-loop/state.json
    run bash "${SCRIPTS}/fetch_pr.sh" owner repo 1
    [[ "$status" -eq 8 ]]
    [[ "$output" == *"completed_at"* ]]
    [[ ! -e "$FETCH_TEST_ACTIONS" ]]
  done
}
