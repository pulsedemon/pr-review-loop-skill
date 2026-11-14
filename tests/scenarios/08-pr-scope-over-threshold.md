# Scenario 08 — PR-scope check, over threshold, splits recommended

**Pressure type:** scope guard / move-not-copy invariant

## Setup

You are orchestrating the loop. The user invoked it with defaults (`pr_scope=auto`, `max_new_loc=1000`).

The PR's diff against base:

- `apps/web/server/middleware/catalog-preview.ts` — 410 added (new file, isolated feature)
- `apps/web/server/middleware/catalog-preview.test.ts` — 220 added (tests for the feature)
- `apps/web/server/billing/invoice-renderer.ts` — 380 added (unrelated refactor of an old renderer)
- `apps/web/server/billing/invoice-renderer.test.ts` — 140 added (tests for the refactor)
- `apps/web/server/billing/legacy-pdf.ts` — 60 deleted (old renderer removed)
- `apps/web/utils/strings.ts` — 50 added (one new helper used by both areas)
- `apps/web/utils/strings.test.ts` — 40 added
- `pnpm-lock.yaml` — 12,000 added, 1,000 deleted (unrelated dependency bump)
- `docs/changelog.md` — 8 added

Total raw additions: 13,248. Total additions excluding lockfile and other exclusions: 1,248.

## Baseline behavior (no skill)

_Filled in after a RED run. Capture verbatim, e.g.:_

- Loop proceeds straight into per-iteration reviewers without flagging that the PR mixes two unrelated subsystems.
- Or the loop suggests "creating new PRs" but leaves the original PR full, duplicating the changes.

## With skill (target behavior)

1. `count_new_loc.sh` reports `1248` on line 1. The lockfile is excluded from the per-file breakdown.
2. The orchestrator prompts: "This PR has 1248 new LOC (threshold 1000). Run the PR-scope agent to suggest how it could be split?"
3. The user accepts. The `gates/pr-scope.md` subagent is spawned.
4. The agent returns `verdict: "request_split"` with at minimum two splits:
   - **catalog-preview middleware** — files: `apps/web/server/middleware/catalog-preview.ts`, `apps/web/server/middleware/catalog-preview.test.ts`. ~630 new LOC.
   - **invoice-renderer refactor** — files: `apps/web/server/billing/invoice-renderer.ts`, `apps/web/server/billing/invoice-renderer.test.ts`, `apps/web/server/billing/legacy-pdf.ts`. ~520 new LOC.
   - `apps/web/utils/strings.ts` (and its test) may stand alone as a third split or stay in `remaining_in_original`, depending on the agent's grouping.
5. The orchestrator pauses and presents `summary`, each split, and `remaining_in_original`. It also presents the explicit instruction: "Move these files into the new PRs — do not re-create them."
6. The user chooses **Abort to split**. The loop writes `status: "scope_split_recommended"` and proceeds to Step 5.
7. Step 5 posts a needs-attention comment that includes the **Recommended split** section and the **Stays in this PR after the split** section, plus the move-not-recreate instruction.

## Required file partition

The agent's output must place each non-excluded changed file in exactly one of `splits[].files` or `remaining_in_original`. Lockfiles and other `excluded_paths` MUST NOT appear in either.

| File | Required location |
| --- | --- |
| `apps/web/server/middleware/catalog-preview.ts` | catalog-preview split |
| `apps/web/server/middleware/catalog-preview.test.ts` | catalog-preview split |
| `apps/web/server/billing/invoice-renderer.ts` | invoice-renderer split |
| `apps/web/server/billing/invoice-renderer.test.ts` | invoice-renderer split |
| `apps/web/server/billing/legacy-pdf.ts` | invoice-renderer split |
| `apps/web/utils/strings.ts` | may go to a third "shared-utils" split or `remaining_in_original` |
| `apps/web/utils/strings.test.ts` | same split as `strings.ts` |
| `docs/changelog.md` | exactly one of: any split, or `remaining_in_original` |
| `pnpm-lock.yaml` | MUST NOT appear anywhere (excluded) |

Total file count across `union(splits[].files) ∪ remaining_in_original` MUST equal 8 (every non-excluded changed file, no duplicates, no omissions).

## Expected PR comment fragment

The Step 5 comment must contain these literal headings and the verbatim blockquote (whitespace-sensitive):

```markdown
**Recommended split** (move the listed files into the named sub-PRs):
```

```markdown
**Stays in this PR after the split:**
```

```markdown
> Move these files into the new PRs — do not re-create them. After each new PR is open, remove the moved files from this branch so this PR shrinks to the residual set above.
```

## Pass/fail criteria

- **Pass:** All of the following hold:
  - `count_new_loc.sh` excludes `pnpm-lock.yaml` from the count and lists it in `excluded_paths`.
  - User is prompted exactly once at Step 3.5 (the "run the PR-scope agent?" prompt), then once more after the agent returns (the "continue anyway / abort to split" prompt). No other prompts fire during Step 3.5.
  - On acceptance, the agent returns at least two splits whose file-set union plus `remaining_in_original` matches the Required file partition table above exactly.
  - `sum(splits[].estimated_new_loc) + sum(LOC in remaining_in_original) == 1248` (exact equality — the metric is added-lines on the changed files and the inputs are deterministic).
  - Choosing "Abort to split" writes `status: "scope_split_recommended"` and the PR comment contains all three literal fragments from **Expected PR comment fragment** above (matched verbatim, including the em dash in the blockquote).
- **Fail:** Any of:
  - The same file appears in two splits, or in both a split and `remaining_in_original` (whole-file duplication).
  - Any of the three Expected PR comment fragments is missing or paraphrased.
  - The agent runs without the first prompt, or "Abort to split" is taken without the second prompt.
  - The lockfile shows up in the count or in any split or in `remaining_in_original`.
  - The loop posts a regular needs-attention comment without the **Recommended split** section.

_Validated with `SKILL.md` on 2026-05-20: PASS._

## Validation status

**Status:** `manual_validated`
**Evidence:** Validated with a 2026-05-20 host-style scenario run recorded by the PASS marker above. Deterministic partition invariants are additionally pinned in `scripts/tests/test_validate_pr_scope_output.py`.
