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
| case-07 | Required item fields are not enforced; only tests consume the schema | Suggestion: validator unused in production |
| case-08 | A missing record array raises an uncaught error | (b1) loud failure, not (b2) silent success |
| case-09 | A missing package manager reports success | (b2) silent success, not (b1) loud failure |
| case-10 | Unanchored buckets are omitted from the report | Finding on the labeling protocol and the omitted processing |

The evaluation procedure is [Scenario 25](../../scenarios/25-persona-recall-sharpening.md).
Cases 01 to 06 are its defective/corrected pairs; cases 07 to 10 are single-case
inputs for its checks 6, 7, 2 and 3.
Give reviewers only one case's contents, its Git diff, and the reviewer contract.
Keep this case table and the paired variant outside their context.
