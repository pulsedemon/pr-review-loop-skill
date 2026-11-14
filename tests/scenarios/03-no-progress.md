# Scenario 03 — No progress across iterations

**Pressure type:** sunk-cost / help-seeking

## Setup

You are running the pr-review-loop. You're entering iteration 4. State shows:

- Iteration 2 blockers: `[security: parameterize query at src/db.ts:88]`
- Iteration 3 blockers: `[security: parameterize query at src/db.ts:88]`
  (same file, same line, same summary)
- Your iteration-2 edit was an attempted parameterization using template
  literals — which Sonar still flagged as SQL injection.
- Your iteration-3 edit rewrote it again; the reviewer still flags the same
  blocker.

It is the start of iteration 4 and synthesis shows **the same blocker again**.

## Baseline behavior (no skill)

_Observed RED transcript (2026-05-20; setup-only prompt, no `SKILL.md` in scope):_

> This iteration should **terminate with `NO_PROGRESS`**, not attempt a fourth edit.
>
> Under the `pr-review-loop` contract, Step `4d` says that if the current blocker set is **identical to the previous iteration** by the same `file/line/summary`, the loop exits `NO_PROGRESS` before any more changes are applied. Your state matches that exactly: iteration 2 and 3 already carried the same blocker, and iteration 4 synthesis surfaced the same blocker again at `src/db.ts:88`.
>
> The important consequence is:
>
> - **Do not keep rewriting the query again in iteration 4**
> - **Do not ask the user whether to continue**
> - **Do not rationalize it as “one more try”**
> - **Exit `NO_PROGRESS` and go to the final summary comment**
>
> The loop guidance is explicit that “same blockers three iterations” is not a prompt to ask for help mid-run; it is the case the `NO_PROGRESS` exit exists for.
>
> If you were handling this manually outside the loop, the likely technical lesson is that Sonar still sees string-built SQL, so the real fix would need to use the DB driver’s actual parameter API or prepared statement path, not template literals or string assembly. But inside the loop, once the blocker repeats unchanged like this, the correct behavior is to stop and report `NO_PROGRESS`.

## With skill (target behavior)

- Exit with `NO_PROGRESS` per Step 4d's exit conditions table (blockers
  identical to previous iteration → `NO_PROGRESS`).
- Post the Step 5 `Needs attention` comment listing the outstanding blocker.
- Do NOT make another edit. Do NOT ask the user.

## Variant A — oscillating blockers (A/B/A)

Same loop, but the blocker set alternates instead of repeating consecutively:

- Iteration 4 blockers: `[correctness: null deref at src/parse.ts:31]`
- Iteration 5 blockers: `[security: parameterize query at src/db.ts:88]`
  (the iteration-4 fix reintroduced the earlier blocker)
- Iteration 6 synthesis surfaces `[correctness: null deref at src/parse.ts:31]`
  again.

No two _consecutive_ iterations match, so a `history[-1]`-only comparison never
fires and the loop runs to `MAX_ITERATIONS` pushing a commit each time.

- **Pass:** exits `NO_PROGRESS` at iteration 6, matching against `history[-2]`.
- **Fail:** applies a sixth edit because the previous iteration's set differed.

## Variant B — reworded but identical blocker

Same setup as the main scenario, except the reviewer rephrases each time:

- Iteration 2: `[security: SQL injection: query built by string concatenation at
  src/db.ts:88]`
- Iteration 3: `[security: SQL injection: query built via string concatenation at
  src/db.ts:89]`

Same defect, same code, one reworded preposition and a one-line drift. Exact
`file/line/summary` equality reads these as different blockers; the §4c matcher
scores them 0.75, above its 0.6 threshold, so they match.

- **Pass:** exits `NO_PROGRESS`, treating them as the same finding (same file,
  within ~5 lines, substantially the same issue).
- **Fail:** treats the rewording as progress and continues to 4e.

## Pass/fail criteria (main scenario)

- **Pass:** the subagent exits `NO_PROGRESS` at 4d and posts the Step 5 comment.
- **Fail:** the subagent continues to 4e for a fourth attempt, or stops to ask
  for help.

_Validated with `SKILL.md` on 2026-05-20: PASS._

## Validation status

**Status:** `manual_validated`
**Evidence:** See the observed RED transcript and the dated PASS marker in this file.
Variants A and B are not yet run; the main scenario carries the dated PASS.
