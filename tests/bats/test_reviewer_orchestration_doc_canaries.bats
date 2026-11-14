#!/usr/bin/env bats

# Canary for docs/reviewer-orchestration.md — the canonical home for
# SKILL.md §4b reviewer-output handling and procedure-expectation rules.
#
# Pins three full-phrase canaries (single words like "shallow" or
# "transient" appear on too many surfaces to be load-bearing):
#
#   1. "Reviewer JSON is transient" — the full sentence that anchors
#      the transient-vs-persisted contract.
#   2. "never pre-create an empty file" — load-bearing rule that
#      prevents a real concurrent-write failure mode (parallel Write
#      refuses if it hasn't Read the path).
#   3. "verdict: approve with missing or empty evidence.files_read" —
#      the actual shallow-review trigger condition consumed by
#      scripts/flag_shallow_reviews.py.
#
# Plus link integrity: the doc must reference the schema and the
# flag_shallow_reviews helper so readers can navigate from prose to
# enforcement.
#
# Mutation-tested before requesting review:
#   - delete the "Reviewer JSON is transient" sentence → that test fails.
#   - rephrase "never pre-create an empty file" → that test fails.
#   - delete the verdict/evidence.files_read sentence → that test fails.

load test_helper

CANONICAL_PATH_FROM_REPO="docs/reviewer-orchestration.md"
CANONICAL="${REPO_ROOT}/${CANONICAL_PATH_FROM_REPO}"

@test "docs/reviewer-orchestration.md exists" {
  [[ -f "$CANONICAL" ]] || {
    echo "canonical reviewer-orchestration doc not found at $CANONICAL"
    return 1
  }
}

@test "docs/reviewer-orchestration.md carries 'Reviewer JSON is transient' canary" {
  grep -qF "Reviewer JSON is transient" "$CANONICAL" || {
    echo "docs/reviewer-orchestration.md missing the load-bearing phrase"
    echo "  'Reviewer JSON is transient'"
    echo "  This sentence anchors the transient-vs-persisted contract."
    return 1
  }
}

@test "docs/reviewer-orchestration.md carries 'never pre-create an empty file' canary" {
  grep -qF "never pre-create an empty file" "$CANONICAL" || {
    echo "docs/reviewer-orchestration.md missing the load-bearing phrase"
    echo "  'never pre-create an empty file'"
    echo "  This rule prevents a real concurrent-write failure mode and"
    echo "  must remain in the canonical home verbatim."
    return 1
  }
}

@test "docs/reviewer-orchestration.md carries the shallow-review trigger phrase" {
  # Note: the doc preserves SKILL.md's inline-code formatting verbatim, so
  # `verdict: approve` and `evidence.files_read` carry backticks. The fixed
  # string below matches that exact rendering.
  grep -qF 'verdict: approve` with missing or empty `evidence.files_read' "$CANONICAL" || {
    echo "docs/reviewer-orchestration.md missing the load-bearing phrase"
    echo "  '\`verdict: approve\` with missing or empty \`evidence.files_read\`'"
    echo "  This is the actual condition that triggers"
    echo "  scripts/flag_shallow_reviews.py; weakening it severs the"
    echo "  prose-to-enforcement link."
    return 1
  }
}

@test "docs/reviewer-orchestration.md links to reviewers/output.schema.json" {
  grep -qE 'reviewers/output\.schema\.json' "$CANONICAL" || {
    echo "docs/reviewer-orchestration.md does not reference reviewers/output.schema.json"
    echo "  the schema is the canonical contract for reviewer output;"
    echo "  the orchestration doc must link to it for navigability."
    return 1
  }
}

@test "docs/reviewer-orchestration.md links to flag_shallow_reviews.py" {
  grep -qE 'flag_shallow_reviews\.py' "$CANONICAL" || {
    echo "docs/reviewer-orchestration.md does not reference scripts/flag_shallow_reviews.py"
    echo "  the helper is what enforces the shallow-review flag;"
    echo "  the orchestration doc must link to it so readers can find"
    echo "  the implementation behind the prose."
    return 1
  }
}
