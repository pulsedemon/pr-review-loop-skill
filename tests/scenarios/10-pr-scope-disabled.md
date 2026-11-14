# Scenario 10 — PR-scope check disabled (`pr_scope=false`)

**Pressure type:** opt-out discipline

## Setup

User invokes the loop with `pr_scope=false`. The PR is large (well over the default `max_new_loc=1000` threshold) — e.g. 5,000 new LOC across application code.

## Baseline behavior (no skill)

_Filled in after a RED run. Capture verbatim, e.g.:_

- The loop still runs `count_new_loc.sh` and prompts the user, ignoring the opt-out.
- Or the loop crashes attempting to call the scope agent.

## With skill (target behavior)

- `count_new_loc.sh` is NOT invoked (verifiable: no `.git/pr-loop/pr-scope.json` file is written, no `pr_scope` block appears in state.json).
- No user prompt fires at Step 3.5.
- The loop proceeds straight from Step 3 to Step 4.

## Pass/fail criteria

- **Pass:** All of the following hold:
  - `.git/pr-loop/pr-scope.json` does not exist after Step 3.5.
  - `state.json` either omits the `pr_scope` block entirely or sets `pr_scope: null`.
  - Zero user prompts during Step 3.5.
  - `count_new_loc.sh` is not invoked (no stderr `# excluded:` lines from this script appear in the run log).
- **Fail:** Any of the four conditions above is violated.

## Validation status

**Status:** `ci_trusted`
**Evidence:** Deterministic Step 3.5 coverage in `scripts/tests/test_pr_scope_step.py` proves `pr_scope=false` skips counting, persistence, and prompting entirely.
