#!/usr/bin/env bats

load test_helper

# Mirrors Codex's skill scan below an installed skill link: it follows
# symlinked directories, skips dot-directories and does not read .gitignore.
skill_md_paths() {
  (
    set -o pipefail
    cd "$1" && find -L . -mindepth 1 -name '.*' -prune -o -name SKILL.md -print | LC_ALL=C sort
  )
}

@test "the checkout holds no SKILL.md besides the root one" {
  # Codex lists each extra copy as another pr-review-loop skill.
  local found
  found="$(skill_md_paths "$REPO_ROOT")"
  [[ "$found" == "./SKILL.md" ]] || {
    echo "SKILL.md copies under the checkout (move them out or rename them):"
    echo "$found"
    return 1
  }
}

@test "the scan reports nested and symlinked copies and skips dot-directories" {
  local tree="$BATS_TEST_TMPDIR/tree" outside="$BATS_TEST_TMPDIR/outside"
  mkdir -p "$tree/docs/run/skill" "$tree/.hidden" "$tree/docs/.cache" "$outside/export"
  touch "$tree/SKILL.md" "$tree/docs/run/skill/SKILL.md" "$tree/.hidden/SKILL.md" \
    "$tree/docs/.cache/SKILL.md" "$outside/export/SKILL.md"
  ln -s "$outside/export" "$tree/docs/linked"

  run skill_md_paths "$tree"
  [ "$status" -eq 0 ]
  [ "$output" = $'./SKILL.md\n./docs/linked/SKILL.md\n./docs/run/skill/SKILL.md' ]
}

@test "the scan fails when find cannot read a directory" {
  [ "$(id -u)" -ne 0 ] || skip "root reads every directory"
  local tree="$BATS_TEST_TMPDIR/tree"
  mkdir -p "$tree/docs/locked"
  touch "$tree/SKILL.md"
  chmod 000 "$tree/docs/locked"

  run skill_md_paths "$tree"
  chmod 755 "$tree/docs/locked"
  [ "$status" -ne 0 ]
}
