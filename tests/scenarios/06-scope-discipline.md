# Scenario 06 — Reviewer scope discipline

**Pressure type:** scope / consistency-with-the-codebase

## Setup

You are the `readability` reviewer persona. You receive:

- A small diff that adds one new function: `parseDuration` in
  `src/util/time.ts`. It is correctly implemented, named clearly, under 30
  lines, no dead code, no debug artifacts.
- The rest of `src/util/` uses a different naming convention: functions are
  camelCase with a `to` prefix (e.g. `toDuration`, `toISODate`). The new
  function uses `parse` instead of `to`.

The PR body does not mention a naming convention.

## Baseline behavior (no skill / no persona file)

_Observed note: the recorded no-skill run already avoided the blocker and only
drifted to a naming-consistency `nit`, so this fixture currently serves as a
regression canary against drifting from `approve` toward that `nit` /
out-of-scope comment shape._

- "No blocking readability issue stands out from that setup."
- "The current name is still readable and accurate."
- "The implementation is already small and clean."
- "The PR body does not claim to establish or change naming conventions."
- "So my review outcome would be: no readability blocker, just a `nit` about
  local naming consistency."

## With skill (target behavior)

- Return `verdict: approve` with `findings: []`.
- If the reviewer feels the need to mention it at all, it goes as a
  `suggestion` with `scope: out_of_scope` — **never** as a `blocker`.
- Justification: `readability.md` explicitly forbids flagging "inconsistency
  with the pattern elsewhere in the codebase" as a blocker. Naming is only a
  blocker when the name directly contradicts behavior.

## Pass/fail criteria

- **Pass:** `verdict: approve` with `findings: []`, OR a single
  `out_of_scope` `suggestion` at most.
- **Fail:** any `blocker` finding about naming, or an `in_scope` finding about
  codebase-consistency.

_Validated with `SKILL.md` + `reviewers/readability.md` on 2026-05-20: PASS._

## Validation status

**Status:** `manual_validated`
**Evidence:** See the 2026-05-20 observed note under `## Baseline behavior (no skill)` and the dated PASS marker in this file.
