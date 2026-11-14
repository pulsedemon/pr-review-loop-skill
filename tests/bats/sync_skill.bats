#!/usr/bin/env bats

load test_helper

# Copy sync_skill.sh into a temp skill tree so BASH_SOURCE resolves there.
install_fixture_skill() {
  local skill_root="${BATS_TEST_TMPDIR}/skill"
  mkdir -p "${skill_root}/scripts"
  cp "${SCRIPTS}/sync_skill.sh" "${skill_root}/scripts/sync_skill.sh"
  chmod +x "${skill_root}/scripts/sync_skill.sh"
  printf '%s' "$skill_root"
}

git_quiet_config() {
  git config user.email "test@example.com"
  git config user.name "test"
  git config commit.gpgsign false
}

@test "exits 0 when skill root is not a git repo" {
  local skill_root
  skill_root=$(install_fixture_skill)
  run bash "${skill_root}/scripts/sync_skill.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"not a git repository"* ]]
}

@test "skips when skill repo has local changes" {
  local skill_root
  skill_root=$(install_fixture_skill)
  cd "$skill_root" || return 1
  git init -q -b main
  git_quiet_config
  echo "init" > README.md
  git add README.md
  git commit -q -m "init"
  echo "dirty" >> README.md
  run bash "${skill_root}/scripts/sync_skill.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"local changes"* ]]
}

@test "honors PR_REVIEW_LOOP_SKIP_SKILL_SYNC" {
  local skill_root
  skill_root=$(install_fixture_skill)
  PR_REVIEW_LOOP_SKIP_SKILL_SYNC=1 run bash "${skill_root}/scripts/sync_skill.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"PR_REVIEW_LOOP_SKIP_SKILL_SYNC"* ]]
}

@test "skips a Cursor copy nested in an unrelated clean git repository" {
  local repo="${BATS_TEST_TMPDIR}/dotfiles"
  local skill_root="$repo/.cursor/skills/pr-review-loop"
  local real_git
  real_git=$(command -v git)
  make_tmp_repo "$repo"
  mkdir -p "$skill_root/scripts"
  cp "${SCRIPTS}/sync_skill.sh" "$skill_root/scripts/sync_skill.sh"
  printf '.cursor/\n' >.gitignore
  git add .gitignore
  git commit -q -m "ignore installs"
  git remote add origin "${BATS_TEST_TMPDIR}/unrelated.git"
  export SYNC_TEST_GIT="$real_git" SYNC_TEST_CALLS="${BATS_TEST_TMPDIR}/calls"
  stub_cmd git '
    case "$1" in
      fetch|pull) echo "$*" >>"$SYNC_TEST_CALLS"; exit 0 ;;
      *) exec "$SYNC_TEST_GIT" "$@" ;;
    esac'

  run bash "$skill_root/scripts/sync_skill.sh"

  [[ "$status" -eq 0 ]]
  [[ "$output" == *"not the git top-level"* ]]
  [[ ! -e "$SYNC_TEST_CALLS" ]]
  [[ -z "$(git status --porcelain)" ]]
}

@test "fast-forwards from origin" {
  local skill_root bare seed c1_sha
  skill_root=$(install_fixture_skill)
  bare="${BATS_TEST_TMPDIR}/origin.git"
  seed="${BATS_TEST_TMPDIR}/seed"
  git init -q --bare "$bare"

  mkdir -p "$seed/scripts"
  cp "${SCRIPTS}/sync_skill.sh" "${seed}/scripts/sync_skill.sh"
  chmod +x "${seed}/scripts/sync_skill.sh"
  cd "$seed" || return 1
  git init -q -b main
  git_quiet_config
  echo v1 > tracked.txt
  git add tracked.txt scripts/sync_skill.sh
  git commit -q -m "c1"
  c1_sha=$(git rev-parse HEAD)
  git remote add origin "$bare"
  git push -q -u origin main

  echo v2 > tracked.txt
  git commit -q -am "c2"
  git push -q origin main

  rm -rf "$skill_root"
  git clone -q -b main "$bare" "$skill_root"
  git -C "$skill_root" reset --hard "$c1_sha"

  ln -s "$skill_root" "${BATS_TEST_TMPDIR}/linked-skill"
  run bash "${BATS_TEST_TMPDIR}/linked-skill/scripts/sync_skill.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"updated"* ]]
  [[ "$(git -C "$skill_root" log -1 --format=%s)" == "c2" ]]
  [[ "$(cat "$skill_root/tracked.txt")" == v2 ]]
}

@test "skips when HEAD is detached" {
  local skill_root
  skill_root=$(install_fixture_skill)
  cd "$skill_root" || return 1
  git init -q -b main
  git_quiet_config
  echo "init" > README.md
  git add README.md scripts/sync_skill.sh
  git commit -q -m "init"
  git checkout --detach -q
  run bash "${skill_root}/scripts/sync_skill.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"detached HEAD"* ]]
}

@test "skips when no origin remote" {
  local skill_root
  skill_root=$(install_fixture_skill)
  cd "$skill_root" || return 1
  git init -q -b main
  git_quiet_config
  echo "init" > README.md
  git add README.md scripts/sync_skill.sh
  git commit -q -m "init"
  run bash "${skill_root}/scripts/sync_skill.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"no origin remote"* ]]
}

@test "continues when pull --ff-only fails" {
  local skill_root bare seed c1_sha
  skill_root=$(install_fixture_skill)
  bare="${BATS_TEST_TMPDIR}/origin.git"
  seed="${BATS_TEST_TMPDIR}/seed"
  git init -q --bare "$bare"

  mkdir -p "$seed/scripts"
  cp "${SCRIPTS}/sync_skill.sh" "${seed}/scripts/sync_skill.sh"
  chmod +x "${seed}/scripts/sync_skill.sh"
  cd "$seed" || return 1
  git init -q -b main
  git_quiet_config
  echo v1 > tracked.txt
  git add tracked.txt scripts/sync_skill.sh
  git commit -q -m "c1"
  c1_sha=$(git rev-parse HEAD)
  git remote add origin "$bare"
  git push -q -u origin main

  echo v2 > tracked.txt
  git commit -q -am "c2"
  git push -q origin main

  rm -rf "$skill_root"
  git clone -q -b main "$bare" "$skill_root"
  git -C "$skill_root" reset --hard "$c1_sha"
  # Create a local diverging commit so ff-only fails
  git -C "$skill_root" config user.email "test@example.com"
  git -C "$skill_root" config user.name "test"
  git -C "$skill_root" config commit.gpgsign false
  echo "diverge" > "$skill_root/local.txt"
  git -C "$skill_root" add local.txt
  git -C "$skill_root" commit -q -m "local diverge"

  run bash "${skill_root}/scripts/sync_skill.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"pull failed; continuing with installed version"* ]]
}

@test "continues when fetch fails" {
  local skill_root
  skill_root=$(install_fixture_skill)
  cd "$skill_root" || return 1
  git init -q -b main
  git_quiet_config
  echo "init" > README.md
  git add README.md scripts/sync_skill.sh
  git commit -q -m "init"
  git remote add origin "${BATS_TEST_TMPDIR}/missing-origin.git"

  local real_git
  real_git="$(command -v git)"
  stub_cmd git "
if [[ \"\$1\" == \"fetch\" ]]; then
  exit 1
fi
exec \"${real_git}\" \"\$@\"
"

  run bash "${skill_root}/scripts/sync_skill.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"fetch failed; continuing with installed version"* ]]
}
