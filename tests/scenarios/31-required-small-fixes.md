# Scenario 31: required small fixes under higher-priority instructions

**Type:** Manual host regression check of §4d.1 routing and §4e required fixes.

## Setup

Iteration 2 of a loop with `max_iterations` 3 reaches §4d.1 with zero blockers after
the adversary, and CI is green. The merged partitions hold:

- an in-scope nit: a comment at `src/retry.ts:14` says "milliseconds" over a value
  in seconds;
- an out-of-scope suggestion: an unused import at `src/util/time.ts:3`, in a file
  the PR does not touch;
- an in-scope suggestion at `src/retry.ts:30`: "make the retry budget
  configurable", which needs a product decision.

Run variant A with no instruction beyond `SKILL.md`. Run variant B with a
higher-priority instruction that requires fixing small flaws a review reveals.

## Checks

1. **A is unchanged.** The no-commit path runs to `SUCCESS` with no edits, and all
   three findings render in the summary as they do without this change.
2. **B fixes before approving.** §4d.1 routes to §4e. The orchestrator fixes the
   comment and the import, leaves the configurable budget alone, and records two
   `fixed_from` records in `addressed[]`. It commits, pushes and reviews iteration
   3 before `SUCCESS`. Only the configurable-budget suggestion renders as open, and
   the import does not render as deferred.
3. **B at the cap.** With `max_iterations` 2, §4e's budget check exits
   `MAX_ITERATIONS`, and the needs-attention summary lists all three.

## Validation status

**Status:** `design_only`
**Missing evidence:** Record a dated host run of both variants. `scripts/tests/test_collect_open_findings.py` pins how a `fixed_from` record settles an open item, but cannot prove the orchestrator routes, fixes or records as described.
