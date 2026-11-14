#!/usr/bin/env bats

# Pins the §4b "Reviewer output handling (orchestrator)" callout in
# SKILL.md. Discovered during the auto-mode review-loop run on PR #20:
# the orchestrator tried to pre-create per-reviewer JSON slots via
# `: > file` and then Write to them, and every parallel Write failed
# because the Write tool refuses to overwrite a path it has not Read.
# In a fully autonomous run with no human to redirect, the loop has no
# graceful terminal-status code for this tool-use mismatch, so the
# guidance has to live in the skill itself.
#
# These three grep-pin assertions guard the three load-bearing pieces:
#   1. The bold heading anchor (so the paragraph isn't quietly deleted).
#   2. The trap-specific directive ("never pre-create an empty file").
#   3. The rationale ("Write refuses to overwrite a path it has not")
#      so a future rewrite that strips the *why* fails the test.

load test_helper

@test "SKILL.md §4b 'Reviewer output handling (orchestrator)' callout exists" {
  grep -F '**Reviewer output handling (orchestrator).**' \
    "${REPO_ROOT}/SKILL.md" >/dev/null || {
    echo "SKILL.md no longer carries the §4b 'Reviewer output handling (orchestrator)' callout"
    echo "  — without it, future auto-mode runs can re-hit the pre-create-then-Write trap"
    echo "  fix: restore the callout in §4b (see commit that added this test)"
    return 1
  }
}

@test "SKILL.md §4b callout pins the 'never pre-create an empty file' directive" {
  grep -F 'never pre-create an empty file' \
    "${REPO_ROOT}/SKILL.md" >/dev/null || {
    echo "SKILL.md §4b callout no longer pins 'never pre-create an empty file'"
    echo "  — the trap-specific directive has been softened or removed"
    echo "  fix: restore the directive in the §4b orchestrator callout"
    return 1
  }
}

@test "SKILL.md §4b callout pins the 'Write refuses to overwrite' rationale" {
  grep -F 'refuses to overwrite a path it has not' \
    "${REPO_ROOT}/SKILL.md" >/dev/null || {
    echo "SKILL.md §4b callout no longer explains *why* pre-create-then-Write fails"
    echo "  — without the rationale, the directive is easy to relax in a future edit"
    echo "  fix: restore the 'Write refuses to overwrite a path it has not Read' clause"
    return 1
  }
}
