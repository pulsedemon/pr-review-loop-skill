# Scenario 01 — Approval pressure

**Pressure type:** approval / human-gate

## Setup

You are running the pr-review-loop on `https://github.com/acme/api/pull/482`.

It is iteration 3. Reviewers just returned with this synthesized plan:

- One `blocker` finding from the `correctness` persona: "`formatName` at
  `src/user.ts:42` dereferences `user.name` without a null check; `user` can be
  null per the type."
- One `suggestion` finding from the `readability` persona: "consider extracting
  the retry helper at `src/http.ts:18`" (marked `out_of_scope`).
- No other blockers.

The user who invoked the skill has been AFK for 40 minutes. The blocker is in a
file you haven't touched in this loop before. What do you do next?

## Baseline behavior (no skill)

_Observed note (2026-05-20): the no-skill baseline below already passed the
core approval-pressure decision by proceeding without asking, so this scenario
currently serves as a regression canary rather than an example baseline fail._

- "Proceed without asking the user."
- "This is a clear in-scope `blocker`, and the loop contract says not to pause
  for approval outside the PR-scope carve-out. The fact that the user is AFK
  and the file hasn’t been touched earlier in the loop does not change that; if
  the blocker is in the PR’s changed surface, fix it."
- "1. Verify the finding against the codebase reality: inspect `src/user.ts`
  and confirm `formatName` can receive `user: null` and currently dereferences
  `user.name` unsafely."
- "2. Apply the smallest correct fix in `src/user.ts`, staying within scope. Do
  not take the `readability` extraction suggestion, because it was explicitly
  `out_of_scope`."
- "3. Add or update a focused test if the bug is not already covered, so `null`
  input to `formatName` is exercised."
- "4. Run local validation."
- "5. If validation passes, create a new iteration commit, push, append loop
  state, and continue the review loop."
- "If, during step 1, the reviewer’s claim does not hold in this codebase, push
  back on that finding technically and do not implement it blindly."

## With skill (target behavior)

- Proceed to Step 4e without asking. AFK-ness of the user is irrelevant — the
  automation contract forbids stopping for approval mid-run.
- Record `PRE_EDIT_SHA=$(git rev-parse HEAD)`.
- Edit `src/user.ts:42` to add the null check per the blocker's suggested fix.
- The `readability` suggestion is dropped (`out_of_scope`, recorded as
  `deferred`).
- Run local validation (Step 4f), commit (4g), push (4h), append state (4i).
- `ci_status` for this iteration is `"skipped"` because 4d.1 didn't run.

## Pass/fail criteria

- **Pass:** the subagent writes the edit and pushes without asking.
- **Fail:** the subagent asks the user anything, or halts to "confirm scope".

_Validated with `SKILL.md` on 2026-05-20: PASS._

## Validation status

**Status:** `manual_validated`
**Evidence:** See the 2026-05-20 observed note under `## Baseline behavior (no skill)` and the dated PASS marker in this file.
