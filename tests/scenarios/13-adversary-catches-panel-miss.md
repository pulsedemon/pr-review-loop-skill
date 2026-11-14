# Scenario 13: Adversary catches a panel miss

**Type:** Manual regression check for `reviewers/adversary.md`. **Not** wired into bats or CI — adversary output is LLM-non-deterministic and a CI gate would flake. Run this by hand when the adversary prompt or any persona prompt changes meaningfully.

## Setup

A small synthetic PR. The diff introduces an off-by-one in `paginate(items, page, page_size)` (uses `<` instead of `<=` for the upper bound), and adds one unit test that only covers `page=1`. Real persona panel run against this diff has historically returned `verdict: approve` from correctness (the change "looks right" from the hunk alone) and from tests (one test exists). The bug surfaces only on the last page when `len(items) % page_size != 0`.

Inputs to provide to the panel agents:

- PR body: "Adds pagination helper. JIRA: BUG-100 (off-by-one observed on the dashboard last-page render)."
- Diff: write the `paginate` hunk from the description above and inline it for the manual run.
- Changed-file list: `src/paginate.ts`, `tests/paginate.test.ts`.

## Mock panel verdicts (passed to the adversary as `adversary_panel_visibility: "verdicts_only"`)

```json
[
  {"name":"correctness","verdict":"approve"},
  {"name":"tests","verdict":"approve"},
  {"name":"security","verdict":"approve"},
  {"name":"performance","verdict":"approve"},
  {"name":"readability","verdict":"approve"},
  {"name":"yagni","verdict":"approve"},
  {"name":"requirements","verdict":"approve"}
]
```

`shallow_review` flag list: `["correctness", "tests"]` (both approved without recording `evidence`).

## Run

Spawn a single subagent with the prompt from `reviewers/adversary.md`, feeding it the inputs above. Use the real PR review skill harness in dry-run mode against a local fixture branch, or invoke the adversary persona directly via your agent host.

## Expected behavior

The adversary should:

1. Populate `evidence.files_read` with at least `src/paginate.ts` and `tests/paginate.test.ts`.
2. Trace callers of `paginate` (grep result expected: dashboard render path).
3. Return `verdict: "request_changes"` with at least one `severity: "blocker", scope: "in_scope"` finding citing the off-by-one bound and missing last-page test coverage.

## Pass criteria

- Adversary returns at least one in-scope blocker pointing at the off-by-one OR at the missing last-page test.
- Adversary cites the JIRA ticket (BUG-100) in the finding `detail` to show it consulted PR context, not just the diff.

## Failure modes worth recording

- Adversary returns `verdict: approve` despite the bug — re-tune `reviewers/adversary.md` (likely needs stronger procedure language or anchoring on the ticket).
- Adversary returns the blocker but with empty `evidence` — procedure section not landing; add a sharper "you MUST populate evidence" line.
- Adversary flags out-of-scope opinions (style, naming) — scope rules need tightening.

## Reminder

If this scenario starts flaking, do **not** wire it into bats to "force consistency". The fix is to the persona prompt, not to a CI gate.

## Validation status

**Status:** `design_only`
**Missing evidence:** Add a dated validation run in this file; adversary behavior remains manual because it is non-deterministic.
