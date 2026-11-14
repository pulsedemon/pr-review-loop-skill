# Test helpers for bats. Sourced by every *.bats file via `load test_helper`.
#
# Conventions:
#   - REPO_ROOT points at the skill repo root.
#   - SCRIPTS points at $REPO_ROOT/scripts.
#   - Each test that needs an isolated git repo calls `make_tmp_repo` in setup().
#   - PATH stubs go in $BATS_TEST_TMPDIR/stubs and are prepended to PATH by
#     `stub_cmd <name> <script body>`.

REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
# Physical path — matches install.sh SOURCE_DIR (pwd -P) for marker assertions.
# shellcheck disable=SC2034  # used by *.bats files that `load` this helper
REPO_ROOT_PHYSICAL="$(cd "${REPO_ROOT}" && pwd -P)"

# Match install.sh inode_of: GNU -c first, then BSD -f.
inode_of() {
  local path="$1"
  stat -c '%i' "$path" 2>/dev/null || stat -f '%i' "$path"
}
# shellcheck disable=SC2034  # used by *.bats files that `load` this helper
SCRIPTS="${REPO_ROOT}/scripts"

# Create a fresh temp git repo under BATS_TEST_TMPDIR/repo and cd into it.
# Initializes an empty commit on branch "main" so HEAD is valid.
make_tmp_repo() {
  local dir="${1:-${BATS_TEST_TMPDIR}/repo}"
  mkdir -p "$dir"
  cd "$dir" || return 1
  git init -q -b main
  git config user.email "test@example.com"
  git config user.name "test"
  # isolate from the user's global signing config; an inherited
  # commit.gpgsign=true would block the empty bootstrap commit below.
  git config commit.gpgsign false
  git config tag.gpgsign false
  git commit -q --allow-empty -m "init"
}

# Copy the skill repo into a temp dir for tests that mutate skill files
# (e.g. corrupting a schema, stripping a version) and then run a script
# against the copy. Excludes dev-only trees — chiefly the 50 MB .venv,
# but also .git and lint caches — none of which any skill script reads.
# A plain `cp -r "$REPO_ROOT"` copies all of it and dominates those tests'
# runtime. Defaults the destination to $BATS_TEST_TMPDIR/skill.
#
# Pass --git to give the copy its own fresh .git: needed when a script run
# against the copy resolves its root via `git rev-parse --show-toplevel`
# (e.g. scripts/regen-check.sh). Without it, git would walk up out of
# the copy and find the real repo, defeating the isolation.
#   copy_skill_tree                  # -> $BATS_TEST_TMPDIR/skill
#   copy_skill_tree "$dest"
#   copy_skill_tree --git "$dest"
copy_skill_tree() {
  local with_git=0
  if [[ "${1:-}" == "--git" ]]; then
    with_git=1
    shift
  fi
  local dest="${1:-${BATS_TEST_TMPDIR}/skill}"
  mkdir -p "$dest"
  # `.git` (no trailing slash) excludes the entry whether it is a directory
  # (normal clone) or a file (a git worktree's gitdir pointer) — a trailing
  # slash would match only the directory form and leak the worktree pointer.
  # Generated from manifests/dev-trees.yaml; an array rather than inline flags
  # because a cog marker inside a backslash-continued command would terminate
  # the continuation.
  # [[[cog: dev_trees_rsync ]]]
  local excludes=(
    --exclude='.git'
    --exclude='.venv/'
    --exclude='.pytest_cache/'
    --exclude='.ruff_cache/'
    --exclude='.worktrees/'
    --exclude='worktrees/'
    --exclude='__pycache__/'
    --exclude='.DS_Store'
    --exclude='.claude/'
    --exclude='.superpowers/'
  )
  # [[[end]]]
  # trailing slash on src: copy contents into dest, not nested under it.
  rsync -a "${excludes[@]}" "${REPO_ROOT}/" "${dest}/"
  if ((with_git == 1)); then
    git -C "$dest" init -q
    git -C "$dest" config user.email "test@example.com"
    git -C "$dest" config user.name "test"
    git -C "$dest" config commit.gpgsign false
    git -C "$dest" add -A
    git -C "$dest" commit -q -m "snapshot" >/dev/null
  fi
}

# Add a stub on PATH. Writes an executable script with the given body and
# prepends its directory to PATH for the rest of the test.
#   stub_cmd gh 'echo "stubbed gh: $*"; exit 0'
stub_cmd() {
  local name="$1"
  local body="$2"
  local stubdir="${BATS_TEST_TMPDIR}/stubs"
  mkdir -p "$stubdir"
  cat >"${stubdir}/${name}" <<EOF
#!/usr/bin/env bash
${body}
EOF
  chmod +x "${stubdir}/${name}"
  PATH="${stubdir}:${PATH}"
  export PATH
}

# Shared sonar prerequisite tests. Accepts the script path relative to $SCRIPTS.
# Usage in a @test: assert_sonar_exits_2_missing_cli "fetch_sonar.sh"
# shellcheck disable=SC2154  # $status and $output are set by bats `run`
assert_sonar_exits_2_missing_cli() {
  local script="$1"
  local p="${BATS_TEST_TMPDIR}/no-sonar"
  mkdir -p "$p"
  for cmd in bash git jq sed awk grep dirname cat; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  PATH="$p" run bash "${SCRIPTS}/${script}" 42
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"sonar"* ]]
}

# shellcheck disable=SC2154  # $status is set by bats `run`
assert_sonar_exits_3_not_authenticated() {
  local script="$1"
  stub_cmd sonar 'case "$1" in
    "auth")
      if [[ "$2" == "status" ]]; then exit 1; fi ;;
  esac
  exit 1'
  run bash "${SCRIPTS}/${script}" 42
  [[ "$status" -eq 3 ]]
}

# shellcheck disable=SC2154  # $status is set by bats `run`
assert_sonar_exits_1_usage_error() {
  local script="$1"
  run bash "${SCRIPTS}/${script}"
  [[ "$status" -eq 1 ]]
}
