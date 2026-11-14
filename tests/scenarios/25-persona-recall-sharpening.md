# Scenario 25: Persona recall sharpening

**Type:** Manual reviewer evaluation with synthetic PR fixtures.

## Setup

Build isolated PR fixtures for the checks below. They exercise schema enforcement, silent validation failures, and documentation drift without requiring private repositories, historical commits, or a labeled corpus. Keep unrelated preconditions valid so each intended defect determines the result.

Use the current persona prompts and record their revisions. These fixtures describe expected behavior; they are not a recorded validation pass or a shipping quota.

## Replay caveat

A merged revision can already contain the fix for a previously reported defect. Evaluate the defective input, not that repaired revision. For a historical replay, identify the exact earlier input; for this scenario, construct the defects below directly in an isolated fixture.

## Checks

1. **Schema enforcement.** Construct `templates/state.schema.json` with prose declaring that `addressed[]` and `deferred[]` entries require `pr` and `cause`, but omit the corresponding item schemas and required fields. Retain a production caller that validates data with the schema, and demonstrate that an entry missing those fields is accepted. Run `type_design` against the diff. Expect a finding quoting both the declared constraint and the missing enforcement. Removing the prose as well would remove the contradiction this check needs.

2. **Silent validation failure.** Construct `scripts/run_local_validation.sh` with a detected stack whose package manager is unavailable and whose missing-tool path returns success. Keep the package manifest valid and all unrelated tools available. Run `blind_spots` against the diff. Expect a category (b2) finding citing the path that reports success although validation did not run.

3. **Documented buckets ignored.** Construct `tools/recall-harness/report.py` without handling the unanchored buckets while retaining their protocol in `tools/recall-harness/label.md`. Include nonempty unanchored input so the omission changes the result. Run `comments` or `readability` against both changed files. Expect a Move C finding identifying the protocol and the omitted processing.

4. **Reviewer schema.** `reviewers/output.schema.json` accepts `"reviewer": "blind_spots"`. The existing `tests/bats/validate_reviewer_output.bats` case "blind_spots reviewer name passes" verifies this deterministic contract.

5. **Clean comparison.** Run the panel against a separate fixture whose code, documentation, and tests agree and contain none of the seeded defects. Expect every selected panel persona to return `verdict: approve` with `findings: []`. Do not use the deliberately broken fixtures as this comparison.

6. **Unused validator.** Repeat Check 1 with no production callers of the validator; only tests reference it. Run `type_design`. Expect a suggestion rather than a blocker, with `detail` containing "validator unused in production". This exercises the reachability gate independently of the positive case.

7. **Loud validation failure.** Construct a separate validator fixture that exits nonzero or raises when validation fails, while its surrounding change has no handler or test for that failure. Run `blind_spots`. Expect category (b1), citing the unhandled failure. A finding on that same path must not classify it as a silent (b2) success. Reusing Check 2 would not exercise this distinction.

## Pass criterion

Compare each finding with the seeded behavior and its evidence, not just its severity or presence:

- Check 1 cites `templates/state.schema.json` and the missing `addressed` or `deferred` required fields.
- Check 2 cites the success result in `scripts/run_local_validation.sh` when the required tool is unavailable.
- Check 3 cites the unanchored-bucket contract and missing processing in the recall harness.
- Check 6 has `severity: suggestion` and the documented "validator unused in production" explanation.
- Check 7 identifies the loud failure under (b1), with evidence showing the nonzero exit or exception, and does not call that path a silent success.

Check 4 is automated. The other checks require actual reviewer responses; document unavailable or incomplete runs as such.

## Notes

Run this optional evaluation after changing the relevant persona behavior. Record fixture contents, prompt revisions, findings, and limitations with any reported result. The [evaluation guidance](../../docs/editing-personas.md#evaluating-reviewer-changes) governs how to use those results.

## Validation status

**Status:** `design_only`
**Missing evidence:** Add a dated run of these synthetic fixtures before claiming their reviewer behavior is validated.
