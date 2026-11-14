# Scenario 17: Evidence-gated solo-adversary promotion

**Type:** CI-trusted traceability scenario for §4d.0.5 + `scripts/promote_findings.py`. This documents the deterministic promotion path already covered by `tests/bats/test_promote_findings.bats`.

## Setup

Synthetic PR: a single file change in `src/handler.ts` introduces a subtle off-by-one only the adversary persona detects. The panel personas all return `approve` with empty `findings`.

Before running `promote_findings.py`, create `src/handler.ts` in the working directory so `_verify_evidence` can confirm the adversary's pointer. The file needs at least 42 lines and must contain the `handlePage` symbol and the snippet `for (let i = 0; i < items.length; i++)`:

```bash
mkdir -p src
{
  for i in $(seq 1 41); do echo "// pad line $i"; done
  echo "function handlePage() { for (let i = 0; i < items.length; i++) { /* off-by-one */ } }"
  for i in $(seq 43 60); do echo "// pad line $i"; done
} > src/handler.ts
```

Without that setup `promote_findings.py` routes the finding to `deferred[]` with `promotion_reason: "evidence_verification_failed"` — that path is covered by scenario 18, not this one.

The adversary's output (constructed manually for this scenario, since the persona is LLM-driven):

```json
{
  "reviewer": "adversary",
  "verdict": "request_changes",
  "findings": [{
    "severity": "suggestion",
    "scope": "in_scope",
    "file": "src/handler.ts",
    "line": 42,
    "summary": "off-by-one on the upper bound",
    "detail": "loop uses < items.length instead of <= for inclusive end",
    "finding_evidence": {
      "file": "src/handler.ts",
      "line": 42,
      "symbol": "handlePage",
      "snippet": "for (let i = 0; i < items.length; i++)"
    }
  }]
}
```

`demoted[]` for this iteration is `[]` (no panelist objected).

## Run

Construct the `promote_findings.py` stdin payload (findings list with the adversary's finding plus `source_reviewers: ["adversary"]`) and invoke:

```bash
cat input.json | python3 scripts/promote_findings.py
```

## Expected output

```json
{
  "blockers": [<the adversary finding>],
  "suggestions": [],
  "nits": [],
  "addressed": [{
    "file": "src/handler.ts",
    "line": 42,
    "summary": "off-by-one on the upper bound",
    "promoted_from": "suggestion",
    "promoted_by": "adversary",
    "promotion_reason": "evidence_gated_solo_adversary",
    "source_reviewers": ["adversary"]
  }],
  "deferred": []
}
```

## Pass criteria

- Finding promoted to `blockers[]`.
- `addressed[]` carries `promotion_reason: "evidence_gated_solo_adversary"`.

## Reminder

This scenario covers the deterministic promotion path. The bats suite `tests/bats/test_promote_findings.bats` already covers it on synthetic inputs; this scenario is for end-to-end sanity against a constructed `state.json` shape.

## Validation status

**Status:** `ci_trusted`
**Proof sources:** `tests/bats/test_promote_findings.bats`
