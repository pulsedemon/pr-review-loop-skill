# Reviewer quality fixtures

These small applications intentionally include defective and corrected variants.
They are evaluation inputs, not shipped helper implementations. Preserve the
seeded defects when changing the surrounding tooling.

| Case | Input | Expected disposition |
| --- | --- | --- |
| case-01 | Required item fields are not enforced | In-scope blocker |
| case-02 | Required item fields are enforced | No finding for that defect |
| case-03 | Missing checker reports success | In-scope blocker |
| case-04 | Missing checker reports failure | No finding for that defect |
| case-05 | Required output buckets are omitted | In-scope blocker |
| case-06 | All required output buckets are rendered | No finding for that defect |

The evaluation procedure is [Scenario 25](../../scenarios/25-persona-recall-sharpening.md).
Give reviewers only one case's contents, its Git diff, and the reviewer contract.
Keep this case table and the paired variant outside their context.
