#!/usr/bin/env bats

load test_helper

@test "the checkout holds no SKILL.md besides the root one" {
  # Codex lists every SKILL.md below the installed skill link as another
  # pr-review-loop skill. It skips dot-directories and nothing else, so
  # gitignored trees are searched on purpose.
  local found
  found="$(cd "$REPO_ROOT" && find . -mindepth 1 -name '.*' -prune -o -name SKILL.md -print)"
  [[ "$found" == "./SKILL.md" ]] || {
    echo "SKILL.md copies under the checkout (move them out or rename them):"
    echo "$found"
    return 1
  }
}
