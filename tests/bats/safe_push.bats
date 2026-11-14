#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
}

# Wire the temp repo to a bare remote and push `main` so origin/<branch> exists.
# Echoes the remote head SHA, which is what safe_push.sh expects as arg 2.
setup_remote() {
  local branch="$1"
  git checkout -q -b "$branch"
  git commit -q --allow-empty -m "branch base"
  git init -q --bare "${BATS_TEST_TMPDIR}/remote.git"
  git remote add origin "${BATS_TEST_TMPDIR}/remote.git"
  git push -q origin "$branch"
  git rev-parse HEAD
}

@test "refuses to push to protected branch (main)" {
  run bash "${SCRIPTS}/safe_push.sh" main deadbeef
  [[ "$status" -eq 10 ]]
  [[ "$output" == *"protected"* ]]
}

@test "refuses when currently on a different branch" {
  git checkout -q -b feature
  run bash "${SCRIPTS}/safe_push.sh" other-branch deadbeef
  [[ "$status" -eq 11 ]]
  [[ "$output" == *"currently on"* ]]
}

@test "usage error without args exits 2" {
  run bash "${SCRIPTS}/safe_push.sh"
  [[ "$status" -eq 2 ]]
}

@test "usage error without the expected-remote-sha arg exits 2" {
  run bash "${SCRIPTS}/safe_push.sh" feat/x
  [[ "$status" -eq 2 ]]
}

@test "pushes when the remote still matches the expected sha" {
  local expected
  expected="$(setup_remote feat/x)"
  git commit -q --allow-empty -m "iteration commit"
  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"
  [[ "$status" -eq 0 ]]
  [[ "$(git --git-dir="${BATS_TEST_TMPDIR}/remote.git" rev-parse refs/heads/feat/x)" == "$(git rev-parse HEAD)" ]]
}

@test "refuses when the remote moved forward (external push)" {
  local expected clone
  expected="$(setup_remote feat/x)"
  # Someone else pushes a commit on top of the branch.
  clone="${BATS_TEST_TMPDIR}/other"
  git clone -q --branch feat/x "${BATS_TEST_TMPDIR}/remote.git" "$clone"
  git -C "$clone" config user.email "other@example.com"
  git -C "$clone" config user.name "other"
  git -C "$clone" commit -q --allow-empty -m "someone else's commit"
  git -C "$clone" push -q origin feat/x

  git commit -q --allow-empty -m "iteration commit"
  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"
  [[ "$status" -eq 12 ]]
  [[ "$output" == *"moved externally"* ]]
}

@test "rejects a rewind immediately before the real push with exit 12" {
  local expected base
  expected="$(setup_remote feat/x)"
  base=$(git rev-parse HEAD^)
  git commit -q --allow-empty -m "iteration commit"
  export PUSH_TEST_GIT PUSH_TEST_REMOTE="${BATS_TEST_TMPDIR}/remote.git" PUSH_TEST_REWIND="$base"
  PUSH_TEST_GIT=$(command -v git)
  stub_cmd git '
    if [[ "$1" == push ]]; then
      "$PUSH_TEST_GIT" --git-dir="$PUSH_TEST_REMOTE" update-ref refs/heads/feat/x "$PUSH_TEST_REWIND"
    fi
    exec "$PUSH_TEST_GIT" "$@"'

  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"

  [[ "$status" -eq 12 ]]
  [[ "$(git --git-dir="$PUSH_TEST_REMOTE" rev-parse refs/heads/feat/x)" == "$base" ]]
}

@test "rejects deletion immediately before the real push without recreating the branch" {
  local expected
  expected="$(setup_remote feat/x)"
  git commit -q --allow-empty -m "iteration commit"
  export PUSH_TEST_GIT PUSH_TEST_REMOTE="${BATS_TEST_TMPDIR}/remote.git"
  PUSH_TEST_GIT=$(command -v git)
  stub_cmd git '
    if [[ "$1" == push ]]; then
      "$PUSH_TEST_GIT" --git-dir="$PUSH_TEST_REMOTE" update-ref -d refs/heads/feat/x
    fi
    exec "$PUSH_TEST_GIT" "$@"'

  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"

  [[ "$status" -eq 12 ]]
  ! git --git-dir="$PUSH_TEST_REMOTE" show-ref --verify --quiet refs/heads/feat/x
}

@test "refuses a non-fast-forward even when the remote matches the expected sha" {
  local expected
  expected="$(setup_remote feat/x)"
  git reset -q --hard HEAD^
  git commit -q --allow-empty -m "diverging local commit"

  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"

  [[ "$status" -eq 12 ]]
  [[ "$output" == *"diverged"* ]]
  [[ "$(git --git-dir="${BATS_TEST_TMPDIR}/remote.git" rev-parse refs/heads/feat/x)" == "$expected" ]]
}

@test "fails closed when git cannot establish ancestry" {
  local expected
  expected="$(setup_remote feat/x)"
  git commit -q --allow-empty -m "iteration commit"
  export PUSH_TEST_GIT
  PUSH_TEST_GIT=$(command -v git)
  stub_cmd git '
    if [[ "$1" == merge-base ]]; then exit 128; fi
    exec "$PUSH_TEST_GIT" "$@"'

  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"

  [[ "$status" -eq 12 ]]
  [[ "$(git --git-dir="${BATS_TEST_TMPDIR}/remote.git" rev-parse refs/heads/feat/x)" == "$expected" ]]
}

@test "pushes the proven commit even when the local branch moves before push" {
  local expected pinned
  expected="$(setup_remote feat/x)"
  git commit -q --allow-empty -m "iteration commit"
  pinned=$(git rev-parse HEAD)
  export PUSH_TEST_GIT PUSH_TEST_REWIND
  PUSH_TEST_GIT=$(command -v git)
  PUSH_TEST_REWIND=$(git rev-parse HEAD~2)
  stub_cmd git '
    if [[ "$1" == push ]]; then
      "$PUSH_TEST_GIT" update-ref refs/heads/feat/x "$PUSH_TEST_REWIND"
    fi
    exec "$PUSH_TEST_GIT" "$@"'

  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"

  [[ "$status" -eq 0 ]]
  [[ "$(git rev-parse HEAD)" == "$PUSH_TEST_REWIND" ]]
  [[ "$(git --git-dir="${BATS_TEST_TMPDIR}/remote.git" rev-parse refs/heads/feat/x)" == "$pinned" ]]
}

@test "honors a rejecting pre-push hook" {
  local expected
  expected="$(setup_remote feat/x)"
  git commit -q --allow-empty -m "iteration commit"
  cat >.git/hooks/pre-push <<'HOOK'
#!/usr/bin/env bash
touch .git/hook-ran
exit 1
HOOK
  chmod +x .git/hooks/pre-push

  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"

  [[ "$status" -eq 1 ]]
  [[ -e .git/hook-ran ]]
  [[ "$(git --git-dir="${BATS_TEST_TMPDIR}/remote.git" rev-parse refs/heads/feat/x)" == "$expected" ]]
}

@test "refuses when the remote was force-pushed backwards over our commits" {
  local base after
  base="$(setup_remote feat/x)"
  git commit -q --allow-empty -m "loop commit"
  git push -q origin feat/x
  after="$(git rev-parse HEAD)"
  git --git-dir="${BATS_TEST_TMPDIR}/remote.git" update-ref refs/heads/feat/x "$base"

  run bash "${SCRIPTS}/safe_push.sh" feat/x "$after"
  [[ "$status" -eq 12 ]]
  [[ "$output" == *"moved externally"* ]]
}

@test "refuses when the fetch cannot reach the remote" {
  local expected
  expected="$(setup_remote feat/x)"
  git remote set-url origin "${BATS_TEST_TMPDIR}/does-not-exist.git"
  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"
  [[ "$status" -eq 12 ]]
  [[ "$output" == *"could not fetch"* ]]
}

@test "refuses when the remote branch was deleted" {
  local expected
  expected="$(setup_remote feat/x)"
  git --git-dir="${BATS_TEST_TMPDIR}/remote.git" update-ref -d refs/heads/feat/x
  git update-ref -d refs/remotes/origin/feat/x
  run bash "${SCRIPTS}/safe_push.sh" feat/x "$expected"
  [[ "$status" -eq 12 ]]
  [[ "$output" == *"REFUSE"* ]]
}
