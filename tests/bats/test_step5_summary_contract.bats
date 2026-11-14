#!/usr/bin/env bats

load test_helper

@test "docs/step5-summary.md pins the single marker-tagged summary comment rule" {
  grep -q '<!-- pr-review-loop-summary -->' "${REPO_ROOT}/docs/step5-summary.md"
  grep -q 'never post multiple summary comments' "${REPO_ROOT}/docs/step5-summary.md"
}

@test "docs/step5-summary.md routes scope_split_recommended to split addendum" {
  grep -q 'SCOPE_SPLIT_RECOMMENDED' "${REPO_ROOT}/docs/step5-summary.md"
  grep -q 'summary_split_addendum.md' "${REPO_ROOT}/docs/step5-summary.md"
}

@test "summary_split_addendum.md keeps the required split headings and move-not-recreate text" {
  grep -qF '**Recommended split** (move the listed files into the named sub-PRs):' \
    "${REPO_ROOT}/templates/summary_split_addendum.md"
  grep -qF '**Stays in this PR after the split:**' \
    "${REPO_ROOT}/templates/summary_split_addendum.md"
  grep -qF '> Move these files into the new PRs — do not re-create them. After each new PR is open, remove the moved files from this branch so this PR shrinks to the residual set above.' \
    "${REPO_ROOT}/templates/summary_split_addendum.md"
}

@test "both summary templates carry the Reviewer comments disposition section" {
  grep -qF '**Reviewer comments:**' "${REPO_ROOT}/templates/summary_ready.md"
  grep -qF '**Reviewer comments:**' "${REPO_ROOT}/templates/summary_needs_attention.md"
}

@test "docs/step5-summary.md documents the Reviewer comments section sourced from comment_ledger" {
  grep -q 'Reviewer comments' "${REPO_ROOT}/docs/step5-summary.md"
  grep -q 'comment_ledger' "${REPO_ROOT}/docs/step5-summary.md"
}

@test "summary_ready.md does not unconditionally claim CI is green" {
  # SUCCESS is reachable with ci_status "skipped" (ci_wait.sh exit 4), so an
  # unconditional "CI is green" would assert a check that never ran.
  ! grep -qF 'All review checks pass and CI is green.' "${REPO_ROOT}/templates/summary_ready.md"
  grep -qF 'No CI checks were found on this PR.' "${REPO_ROOT}/templates/summary_ready.md"
}

@test "docs/step5-summary.md routes the ready-template CI sentence on ci_status" {
  grep -q 'ci_status' "${REPO_ROOT}/docs/step5-summary.md"
  grep -qF 'No CI checks were found on this PR.' "${REPO_ROOT}/docs/step5-summary.md"
}

@test "dry-run terminal never writes to the PR" {
  # The load-bearing dry_run guarantee. These are prose instructions a host
  # follows, so nothing else fails if the wording drifts back to posting.
  grep -qF 'never** on the §4c `DRY_RUN_COMPLETE` path' "${REPO_ROOT}/SKILL.md"
  grep -q 'DRY_RUN_COMPLETE' "${REPO_ROOT}/docs/step5-summary.md"
  grep -qF 'not** run on that one' "${REPO_ROOT}/docs/comment-handling.md"
}

@test "dry-run reports in session rather than printing a setup-error message" {
  # SETUP_ERROR and DRY_RUN_COMPLETE share the no-comment path but not the
  # output: grouping them under "print a stderr message" loses the findings.
  ! grep -qF 'do not** post a PR comment — print a stderr message and return.' \
    "${REPO_ROOT}/SKILL.md"
  grep -qF 'reports the synthesized partitions in the session' "${REPO_ROOT}/SKILL.md"
}

@test "dry-run records its findings via the 4i no-commit path" {
  grep -qF 'invoke §4i on its no-commit path' "${REPO_ROOT}/SKILL.md"
  grep -qF 'synthesized `findings` are recorded (not `[]`)' "${REPO_ROOT}/SKILL.md"
}

@test "step5 routing covers the all-skipped CI case, not just no-checks" {
  # ci_wait.sh exits 0 when every check concluded as `skip`, recording
  # ci_status "success". Routing on that alone renders "CI is green." for
  # checks that never ran — the same false claim the exit-4 rule removes.
  grep -qF 'only skipped' "${REPO_ROOT}/docs/step5-summary.md"
  grep -qF 'last_ci_status.json' "${REPO_ROOT}/docs/step5-summary.md"
}
