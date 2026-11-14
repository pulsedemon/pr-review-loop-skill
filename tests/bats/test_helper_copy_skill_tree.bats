#!/usr/bin/env bats

load test_helper

setup() {
  WORKTREE_PATH="${BATS_TEST_TMPDIR}/worktree"
  DEST_PATH="${BATS_TEST_TMPDIR}/copied-skill"
}

teardown() {
  if [[ -d "${WORKTREE_PATH}" ]]; then
    git -C "${REPO_ROOT}" worktree remove --force "${WORKTREE_PATH}" >/dev/null 2>&1 || true
  fi
}

@test "copy_skill_tree excludes .git when the source repo is a worktree" {
  run git -C "${REPO_ROOT}" worktree add --detach "${WORKTREE_PATH}" HEAD
  [ "$status" -eq 0 ]
  [ -f "${WORKTREE_PATH}/.git" ]

  run bash -c '
    set -euo pipefail
    export BATS_TEST_DIRNAME="$1/tests/bats"
    export BATS_TEST_TMPDIR="$2"
    # shellcheck source=/dev/null
    source "$1/tests/bats/test_helper.bash"
    copy_skill_tree "$3"
  ' bash "${WORKTREE_PATH}" "${BATS_TEST_TMPDIR}/subtmp" "${DEST_PATH}"
  [ "$status" -eq 0 ]
  [ ! -e "${DEST_PATH}/.git" ]
}
