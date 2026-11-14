# Scenario 12 — yagni reviewer fetches sibling-PR diffs

**Pressure type:** sibling-PR context discipline / no false single-use flags

## Setup

The PR under review (call it PR #B) has a body that references a sibling PR #A in the same repo:

```
Part of #A — adds the producer side. The consumer lives in #A.
```

PR #B's diff (changes only):

- `src/lib/eventBus.ts` — adds a new exported function `publishWidgetCreated(widget: Widget)` that calls an existing `bus.publish(...)` underlying API. The function is exported and is **not called by any code in PR #B itself**.

PR #A's diff (the sibling, already open):

- `src/features/widgetCreator.tsx` — `import { publishWidgetCreated } from "../lib/eventBus"` and a call site inside the component.

Without sibling-PR context, the yagni reviewer's "single-use wrapper" rule would fire on `publishWidgetCreated` — it forwards arguments to `bus.publish` and has zero callers within PR #B alone.

## Baseline behavior (no skill)

_Filled in after a RED run. Capture verbatim, e.g.:_

- yagni reviewer flags `publishWidgetCreated` as a dead wrapper, recommending inlining. The author has to push back manually, citing PR #A.

## With skill (target behavior)

The yagni reviewer, before producing any findings:

1. Scans the PR body and detects `Part of #A`.
2. Runs `gh pr diff A` (and `gh pr view A --json title,body,files`) to fetch the sibling's diff.
3. Identifies `import { publishWidgetCreated }` in PR #A — a real consumer.
4. Treats `publishWidgetCreated` as in-scope context, **not** as a dead wrapper.

Final reviewer output for PR #B contains zero `blocker` or `suggestion` findings about `publishWidgetCreated`. The reviewer returns `verdict: "approve"` (or returns other unrelated findings, but not this one).

## Pass/fail criteria

- **Pass:** All of the following hold:
  - The reviewer's transcript shows a `gh pr diff <A>` (or `gh pr view <A>`) call before any finding is emitted.
  - `publishWidgetCreated` is NOT in any `findings[].file/line/summary`.
  - The reviewer's verdict for PR #B is `approve` (assuming nothing else is wrong with PR #B).
- **Fail:** Any of:
  - The reviewer never fetches the sibling diff.
  - `publishWidgetCreated` appears as a `blocker` or `suggestion` with rationale "single-use wrapper" or "no caller in the diff".
  - The reviewer's `detail` for any finding on `publishWidgetCreated` claims "no caller exists" without mentioning the sibling-PR check.

## Additional sibling-PR forms to exercise

The fixture above uses `Part of #A`. The reviewer must handle all the signals listed in `reviewers/yagni.md` § "Context gathering — sibling PRs". A complete discipline run should re-execute this scenario substituting the body line with each of:

- `Depends on #A`
- `Companion to #A — the consumer lives there`
- A bare URL: `https://github.com/<owner>/<repo>/pull/A`
- A shared parent ticket: `ABC-123` (when the ticket links to both PRs)
- A series branch name: e.g. PR #B is on `feature/foo-2of3` and PR #A is on `feature/foo-1of3`

For each variant the reviewer must reach the same conclusion (no false single-use flag). If a sibling-PR signal is present but the sibling cannot be fetched (e.g. it's in a different repo), the reviewer must say so explicitly in any finding's `detail` rather than silently assuming the artifact is dead.

## Validation status

**Status:** `design_only`
**Missing evidence:** Add a dated validation run or deterministic automation covering sibling-PR context handling for the yagni reviewer.
