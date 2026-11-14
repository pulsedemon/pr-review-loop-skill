# Scenario 19: Panel objection suppresses solo-adversary promotion

**Type:** Manual traceability scenario for the §4d.0.5 gate condition that no panelist objected within ±5 lines. The deterministic gate logic is covered by `tests/bats/test_promote_findings.bats`, but this scenario also cares about the upstream `demoted[]` handoff from synthesis.

## Setup

Same shape as scenario 17 (adversary catches an off-by-one only the panel missed), but with one twist: in the same iteration, `correctness` raised a finding at `src/handler.ts:40` and the synthesizer dropped it as `not_a_problem` — recording it in `demoted[]`. The adversary's `finding_evidence.line` is 42, within ±5 of 40, so the gate should suppress promotion.

Construct the stdin payload manually:

```json
{
  "panel_findings": [],
  "adversary_findings": [{
    "reviewer": "adversary",
    "severity": "suggestion",
    "scope": "in_scope",
    "file": "src/handler.ts",
    "line": 42,
    "summary": "off-by-one on the upper bound",
    "detail": "loop uses < items.length instead of <=",
    "source_reviewers": ["adversary"],
    "finding_evidence": {
      "file": "src/handler.ts",
      "line": 42,
      "symbol": "handlePage",
      "snippet": "for (let i = 0; i < items.length; i++)"
    }
  }],
  "suggestion_promotion_threshold": 2,
  "adversary_promotion": true,
  "adversary_solo_promotion": true,
  "demoted": [{
    "file": "src/handler.ts",
    "line": 40,
    "summary": "panelist thought this was wrong but synthesizer dropped",
    "reviewer": "correctness",
    "reason": "not_a_problem",
    "note": "iteration synthesizer judged this as a false positive"
  }]
}
```

## Run

```bash
cat input.json | python3 scripts/promote_findings.py
```

## Expected output

```json
{
  "blockers": [],
  "suggestions": [<the adversary finding>],
  "nits": [],
  "addressed": [],
  "deferred": []
}
```

## Pass criteria

- Adversary finding stays in `suggestions[]` (NOT in `blockers[]`).
- No `addressed[]` provenance entry.
- No `promotion_reason: "evidence_gated_solo_adversary"` anywhere in the output.

## Why this scenario matters

The gate's "no panelist objected" check is the only thing standing between v2's solo-adversary path and a false-positive blocker that the panel already considered and rejected. Bats coverage (`tests/bats/test_promote_findings.bats` "solo-adversary gate fails when panelist objected within ±5 lines") exercises the deterministic logic; this scenario is the end-to-end audit-trail check that the §4c synthesizer's `demoted[]` recordkeeping actually flows into the gate.

## Reminder

Do not wire into bats — the deterministic path is already covered there. This scenario validates the cross-iteration soft contract on synthesizer recordkeeping.

## Validation status

**Status:** `design_only`
**Missing evidence:** Add deterministic coverage that proves the §4c synthesizer's `demoted[]` recordkeeping reaches the solo-adversary gate end to end, or record a dated manual validation run for that full handoff.
