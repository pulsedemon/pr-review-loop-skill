# Scenario 18: Evidence verification failure path

**Type:** CI-trusted traceability scenario for `scripts/promote_findings.py` evidence verification (spec §2). This documents the deterministic failure path already covered by `tests/bats/test_promote_findings.bats`.

## Setup

Same shape as scenario 17, but the adversary's `finding_evidence.line` is `999999` (well past the file's line count). The file `src/handler.ts` exists but only has 60 lines.

## Run

```bash
cat input.json | python3 scripts/promote_findings.py
```

## Expected output

```json
{
  "blockers": [],
  "suggestions": [],
  "nits": [],
  "addressed": [],
  "deferred": [{
    "file": "src/handler.ts",
    "line": 42,
    "summary": "off-by-one on the upper bound [evidence_verification_failed: line 999999 out of bounds (file has 60 lines)]",
    "promoted_from": "suggestion",
    "promoted_by": "adversary",
    "promotion_reason": "evidence_verification_failed",
    "source_reviewers": ["adversary"]
  }]
}
```

## Pass criteria

- Finding lands in `deferred[]` as a provenance object.
- `promotion_reason` is `"evidence_verification_failed"`.
- The verification failure reason is captured (in `summary` per the implementation note in Task 5).

## Other failure modes to try

- `finding_evidence.file` does not exist → expect `evidence_verification_failed: file not found: ...`
- `finding_evidence.symbol` not in the file → expect `evidence_verification_failed: symbol '<x>' not present in ...`
- `finding_evidence.snippet` not in the file → expect `evidence_verification_failed: snippet not present in ...`

## Reminder

Bats coverage of these failure modes is in `tests/bats/test_promote_findings.bats`. This scenario is the end-to-end audit-trail check.

## Validation status

**Status:** `ci_trusted`
**Proof sources:** `tests/bats/test_promote_findings.bats`
