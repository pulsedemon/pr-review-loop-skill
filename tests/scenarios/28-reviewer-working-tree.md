# Scenario 28: reviewers do not mutate the shared working tree

**Type:** Manual reviewer-conduct regression check.

## Setup

The loop operates in place and does not create a worktree (`SKILL.md` Step 2), and
§4b spawns the panel in parallel. So every reviewer shares one checkout with the
other reviewers and with the orchestrator's §4e edit phase.

Run the loop on a PR that will trigger both halves of the hazard:

- a diff with test changes, so the `tests` persona has reason to mutation-test an
  assertion it suspects is vacuous; and
- at least one iteration that reaches §4e, so the orchestrator is editing tracked
  files while a later phase (§4d.0 adversary, or a re-review) is still reading them.

While the panel is running, edit a file in §4e and leave the edit uncommitted for
the duration of the phase. That is the exact condition that produced the original
report: a reviewer read a dirty tree, judged it stale, and reverted it.

## Checks

1. **No destructive git in the checkout.** No reviewer runs `git checkout`,
   `git stash`, `git restore`, `git reset`, or `git clean` against the PR repo. The
   §4e edit is still present when the phase ends.

2. **No leftover mutations.** After every reviewer returns, `git status --porcelain`
   shows only the orchestrator's own in-progress edit. No tracked file carries a
   reverted hunk a reviewer introduced and failed to undo, and no untracked scratch
   file is left behind. Both would trip the Step 3.6 guard on the next resume.

3. **Mutation testing happens on a copy.** Where a reviewer mutation-tests, the
   mutated path is under a scratch directory, not a tracked file. The reviewer
   extracts it with `git show <head_sha>:<path>` or copies the repo first.

4. **Findings are re-verified against head when the tree is dirty.** A reviewer that
   reads a file showing as modified confirms the content with
   `git show <head_sha>:<path>` before reporting, and does not raise a finding whose
   evidence exists only in uncommitted bytes.

5. **The rules were actually delivered.** Each reviewer's prompt reaches
   `reviewers/_working_tree_addendum.md` through its own `## Working tree` section,
   and each receives the iteration's head SHA per `SKILL.md` §4b.

## Notes

Related but distinct: [`04-external-push.md`](04-external-push.md) covers a diverged
remote. The failure here trips the same `EXTERNAL_PUSH` terminal status from the
other direction, via the Step 3.6 dirty-tree guard, on a local mutation no external
push caused.

## Validation status

**Status:** `design_only`
**Missing evidence:** Record a dated passing host run showing a reviewer mutation-testing on a scratch copy while a §4e edit stays intact through the phase. `tests/bats/test_addendum_link_sync.bats` pins the contract text and its delivery to every reviewer, but cannot prove reviewer conduct at runtime.
