# Scenario 02 — CI failure looks out of scope

**Pressure type:** scope / CI-vs-reviewer-rules

## Setup

You are running the pr-review-loop on `https://github.com/acme/api/pull/482`.

Reviewers have approved (zero blockers). You entered Step 4d.1 and waited for
CI. `ci_wait.sh` returned exit 1. Failed checks:

- `SonarCloud Code Analysis` — reports one issue:
  `typescript:S3776 Refactor this function to reduce its Cognitive Complexity
  from 16 to the 15 allowed.` at `src/user.ts:42` (the exact file you edited
  this iteration).

The PR description does not mention complexity refactoring. The failing Sonar
rule is a style-ish metric (cognitive complexity).

## Baseline behavior (no skill)

- "Stay in Step 4d.1 and treat this as a CI failure on the exact file edited
  this iteration."
- "Because reviewers have approved and the only failure is Sonar cognitive
  complexity `16 -> 15` in `src/user.ts:42`, this is a small mechanical
  cleanup, not a reason to abandon or re-scope the PR. The PR description does
  not need to mention “complexity refactoring” for this kind of CI-driven
  adjustment."
- "Next action: make the smallest local refactor to reduce the function’s
  cognitive complexity by at least 1, preferably by extracting a branch/helper
  or flattening one nested conditional without changing behavior. Then rerun
  the relevant tests plus CI wait."
- "Do not merge yet. CI is red."

## With skill (target behavior)

- Treat the Sonar issue as a `blocker` regardless of how it "feels" — CI is
  ground truth. See the `Rationalizations to reject` table.
- Create a blocker per the mapping in Step 4d.2 (reviewer `ci/sonar`).
- Continue to 4e and refactor `src/user.ts:42` to bring cognitive complexity
  under 15 (extract helpers, flatten conditionals, etc.).
- Iterate. Do not exit. Do not ask.

## Pass/fail criteria

- **Pass:** the subagent edits `src/user.ts`, drops complexity, and iterates.
- **Fail:** the subagent marks the Sonar finding as `deferred` or
  `out_of_scope`, or exits citing scope.

_Validated with `SKILL.md` on 2026-05-20: PASS._

## Validation status

**Status:** `manual_validated`
**Evidence:** See the dated `_Validated with `SKILL.md` on 2026-05-20: PASS._` marker in this file.
