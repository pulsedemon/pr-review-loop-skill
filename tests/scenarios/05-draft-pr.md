# Scenario 05 — Draft PR

**Pressure type:** draft gating

## Setup (case A — default)

The user says:

> Use the pr-review-loop skill on https://github.com/acme/api/pull/902

`gh pr view 902` reports `isDraft: true`. The user passed no extra parameters.

## With skill (target behavior, case A)

- Step 1's precondition check aborts because `isDraft` is true and
  `allow_draft` is false (the default).
- Do not initialize state (Step 3 doesn't run).
- Return cleanly with a short message like "PR #902 is a draft; rerun with
  `allow_draft=true` to override." Do not post a PR comment.

## Baseline behavior (no skill, case A)

_Filled in after a RED run. Capture what the subagent does when it sees
`isDraft: true` with no guidance and no explicit opt-in: does it proceed
anyway? Ask the user? Invent a parameter? Record the verbatim behavior._

## Setup (case B — opt-in)

The user says:

> Run pr-review-loop on https://github.com/acme/api/pull/902 with
> `allow_draft=true`.

Same PR. Same metadata.

## With skill (target behavior, case B)

- Step 1 accepts the invocation; `allow_draft=true` disables the draft abort.
- Proceed normally into Step 2, 3, 4.

## Baseline behavior (no skill, case B)

_Filled in after a RED run. Capture what the subagent does when the user
explicitly passes `allow_draft=true` but the skill is not loaded: does it
ignore the unknown parameter, abort on draft anyway, proceed silently?
Record the verbatim behavior._

## Pass/fail criteria

- **Case A pass:** aborts with a clear message, no state written.
- **Case A fail:** starts the loop despite the draft status, or stops to ask
  whether to continue.
- **Case B pass:** runs normally.
- **Case B fail:** still aborts despite the explicit opt-in.

## Validation status

**Status:** `design_only`
**Missing evidence:** Add a dated manual validation run to this file or deterministic coverage for both the draft-default abort path and the `allow_draft=true` opt-in path.
