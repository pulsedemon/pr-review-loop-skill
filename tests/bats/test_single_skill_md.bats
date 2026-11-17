#!/usr/bin/env bats

load test_helper

# Mirrors Codex's skill scan below an installed skill link: it follows
# symlinked directories, skips dot-directories and does not read .gitignore.
skill_md_paths() {
  (cd "$1" && find -L . -mindepth 1 -name '.*' -prune -o -name SKILL.md -print | LC_ALL=C sort)
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
  mkdir -p "$tree/docs/run/skill" "$tree/.hidden" "$outside/export"
  touch "$tree/SKILL.md" "$tree/docs/run/skill/SKILL.md" "$tree/.hidden/SKILL.md" \
    "$outside/export/SKILL.md"
  ln -s "$outside/export" "$tree/docs/linked"

  run skill_md_paths "$tree"
  [ "$status" -eq 0 ]
  [ "$output" = $'./SKILL.md\n./docs/linked/SKILL.md\n./docs/run/skill/SKILL.md' ]
}
