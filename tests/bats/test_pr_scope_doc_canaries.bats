#!/usr/bin/env bats

# Canary for docs/pr-scope.md — the canonical home for SKILL.md §3.5
# four-substep mechanics, verdict branches, non-interactive defaults,
# and the resume contract.
#
# Pins:
#   1. The doc exists at the expected path.
#   2. All four `pr_scope.user_decision` values appear (not_prompted,
#      declined_agent, continue, abort) — these are the resume-skip
#      branches; missing one means the resume contract is unreadable.
#   3. The three agent verdicts appear (under_threshold, atomic,
#      request_split) — the schema's `pr_scope.verdict.enum`.
#      `declined_agent` is a `user_decision` value (covered by the
#      check above), not a verdict.
#   4. Both non-interactive defaults appear ("declined_agent" for the
#      Yes/No prompt, "SCOPE_SPLIT_RECOMMENDED" for the
#      request_split prompt).
#
# Mutation-tested before requesting review:
#   - delete one verdict from the table → "missing verdict" failure.
#   - delete one user_decision value → "missing user_decision" failure.
#   - delete the SCOPE_SPLIT_RECOMMENDED non-interactive default →
#     "missing non-interactive abort default" failure.

load test_helper

CANONICAL_PATH_FROM_REPO="docs/pr-scope.md"
CANONICAL="${REPO_ROOT}/${CANONICAL_PATH_FROM_REPO}"

@test "docs/pr-scope.md exists" {
  [[ -f "$CANONICAL" ]] || {
    echo "canonical PR-scope mechanics doc not found at $CANONICAL"
    return 1
  }
}

@test "docs/pr-scope.md names every pr_scope.user_decision value" {
  local v
  for v in not_prompted declined_agent continue abort; do
    grep -qwF "$v" "$CANONICAL" || {
      echo "docs/pr-scope.md missing user_decision value '${v}'"
      echo "  the resume-skip contract relies on all four values being present"
      return 1
    }
  done
}

@test "docs/pr-scope.md names every agent verdict (under_threshold, atomic, request_split)" {
  local v
  for v in under_threshold atomic request_split; do
    grep -qwF "$v" "$CANONICAL" || {
      echo "docs/pr-scope.md missing verdict '${v}'"
      echo "  the verdict-branch table must list every value the agent can return"
      echo "  (declined_agent is a user_decision, not a verdict — covered by the user_decision canary above)"
      return 1
    }
  done
}

@test "docs/pr-scope.md documents both non-interactive defaults" {
  grep -qE 'declined_agent' "$CANONICAL" || {
    echo "docs/pr-scope.md missing the 'declined_agent' non-interactive default"
    return 1
  }
  grep -qE '(SCOPE_SPLIT_RECOMMENDED|scope_split_recommended)' "$CANONICAL" || {
    echo "docs/pr-scope.md missing the SCOPE_SPLIT_RECOMMENDED non-interactive abort default"
    echo "  this is the contract for the request_split prompt's non-interactive path"
    return 1
  }
  grep -qE 'Non-interactive' "$CANONICAL" || {
    echo "docs/pr-scope.md missing the 'Non-interactive' definition section"
    return 1
  }
}
