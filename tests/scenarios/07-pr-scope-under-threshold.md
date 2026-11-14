# Scenario 07 — PR-scope check, under threshold

**Pressure type:** silent path / no false prompts

## Setup

You are orchestrating the loop. The user invoked it with defaults (`pr_scope=auto`, `max_new_loc=1000`). After Step 3 completes you reach Step 3.5.

The PR's diff against base:

- `src/feature/foo.ts` — 180 added, 0 deleted
- `src/feature/foo.test.ts` — 90 added, 0 deleted
- `README.md` — 12 added, 0 deleted
- `package-lock.json` — 4,200 added, 100 deleted (a dependency bump that landed alongside the feature)

Total raw additions: 4,482. Total additions excluding lockfile: 282.

## Baseline behavior (no skill)

_Filled in after a RED run. Capture verbatim, e.g.:_

- Loop prompts the user about scope despite the genuine new-code total being ~280 LOC, because the agent eyeballed the raw diff and saw a four-thousand-line lockfile bump.
- Or the loop ignores scope entirely and the user has no opt-in.

## With skill (target behavior)

- `bash scripts/count_new_loc.sh <base>` reports `282` on stdout line 1 and emits exactly three TSV rows on lines 2–4 (one each for `src/feature/foo.ts`, `src/feature/foo.test.ts`, `README.md`). No row references `package-lock.json`.
- Stderr emits exactly one line: `# excluded: package-lock.json`.
- The orchestrator records, in both `.git/pr-loop/pr-scope.json` and `state.pr_scope`:

  ```json
  {
    "threshold": 1000,
    "new_loc_total": 282,
    "per_file": [
      {"added": 180, "deleted": 0, "path": "src/feature/foo.ts"},
      {"added": 90,  "deleted": 0, "path": "src/feature/foo.test.ts"},
      {"added": 12,  "deleted": 0, "path": "README.md"}
    ],
    "excluded_paths": ["package-lock.json"],
    "verdict": "under_threshold",
    "user_decision": "not_prompted"
  }
  ```

- **No user prompt fires.** Step 3.5 finishes silently.
- The loop proceeds straight to Step 4.

## Pass/fail criteria

- **Pass:** All of the following hold:
  - Step 3.5 runs `count_new_loc.sh`, persists the result, and continues to Step 4 with **zero** user prompts.
  - The lockfile is excluded from `per_file` and listed verbatim in `excluded_paths`.
  - `pr_scope.verdict == "under_threshold"` and `pr_scope.user_decision == "not_prompted"`.
- **Fail:** Any user prompt fires. Or the count includes the lockfile (inflated total leads to a false-positive prompt). Or `pr-scope.json` is not written. Or `excluded_paths` is empty / missing the lockfile.

## Validation status

**Status:** `ci_trusted`
**Evidence:** Deterministic Step 3.5 coverage in `scripts/tests/test_pr_scope_step.py` proves the under-threshold path skips prompts and persists `user_decision: "not_prompted"`.
