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

## Paired panel procedure

The [reviewer-quality fixtures](../fixtures/reviewer-quality/README.md) contain
three defective/corrected pairs. Export each case into its own Git repository
and make a base-to-head diff containing that case alone. Give reviewers its
README as the PR body, the diff, head SHA, changed files, persona prompt,
linked addenda, and output schema. Keep the case table, expected answers,
paired variant, and other arm's responses outside their context.

Before dispatch, run each case's command checks independently. The defective
variants must fail on their stated seed; their counterparts must pass. Freeze
the tracked inputs, skill revision, effective promotion settings, actual model
and effort, and prompt format. Exclude generated caches from the input export.

Compare the default panel with `approvers_required=correctness,tests,security`.
Each arm gets one independent panel pass and one fresh adversary with that
arm's full raw responses. Alternate arm order by case. Validate responses with
`validate_reviewer_output.py`, dedupe with the canonical matcher, and apply
`promote_findings.py` with the frozen settings. Preserve raw findings and final
partitions.

Replace a response that fails schema validation once: launch a fresh session of
the same reviewer with the same prompt and settings, inside the same reviewer
budget. Decide it from the validator's result alone. Keep the invalid response,
and count the replacement's time and usage in that arm. A second invalid
response, a missing response, a changed route, or a failed launch makes the
pair incomplete; do not resample it or count it as approval.

Hide arm and reviewer identities before judging findings against the frozen
code. Group repeated reports of the same defect and record its affected
locations. Record usefulness, low-value findings, false findings, unsupported
blocker classifications, and each seed's final partition. A seed mentioned
only as a suggestion does not count as a retained blocker.

Start with cases 01-04. Only after complete pilot pairs retain both defects as
blockers without additional false blockers in the smaller arm, run cases 05-06
as frozen holdouts. The bound is six pairs, at most 96 reviewer invocations
including adversaries; replacement sessions are additional and reported. Do not
tune prompts or expand the sample mid-run.
Recommend the smaller override only when all six pairs complete, all seeded
blockers survive in both arms, and it reduces measured usage or time without
additional false blockers or low-value findings. Keep the default panel intact.

## Observed comparison, 2026-11-14

The Codex parent used Witch-routed `gpt-6.1-sol`, high effort, for both panels
and adversaries. Inputs and skill were frozen at
`90e55936e7b8584562c6856033e47cbf7361073a`, with promotion settings
`0/false/false`. Three paired cases completed. Case 04's smaller arm completed,
but its full panel had registration timeouts and one native approval-review
failure before launch. That pair is incomplete; no holdouts ran.

| Case | Full: useful / low-value / false | Smaller: useful / low-value / false | Seed retained as blocker |
| --- | --- | --- | --- |
| 01, schema enforcement | 3 / 1 / 0 | 4 / 1 / 0 | Both arms |
| 02, corrected schema | 3 / 2 / 0 | 2 / 3 / 0 | No schema-seed finding |
| 03, unavailable checker | 2 / 1 / 0 | 1 / 1 / 0 | Both arms |

These are unique issue counts per case and arm after blinded judgment, not
raw report counts. Both arms also classified a test for the inert greeting
fixture as a blocker. That gap is factual but low-value, with no supported
reason to block the validation command. It is counted as low-value above and
as an unsupported blocker separately.

The corrected schema control still had unseeded numeric-input defects, and
the validator fixtures failed developer Ruff 0.16.0 despite passing the
repository-pinned Ruff 0.15.13. Those findings were reproduced and fixed in the
shipped fixtures after freezing the comparison. They remain useful findings
in this record; the original controls were not clean approvals. The two arms
missed different additional defects. No promotion occurred, and every returned
review response passed schema validation. The completed groups left their
tracked fixture checkouts unchanged.

For the three complete pairs, summed reviewer-phase time was 643.3 seconds
for the full panel and 500.5 seconds for the smaller panel. Each phase runs
from its first report-file creation to its last final write; panel and
adversary durations are added, excluding parent orchestration gaps. This is
one-pass timing, not total loop duration or a cost estimate. Token and monetary
usage were unavailable.

The result does not support a smaller-panel recommendation: the required
sample is incomplete, its controls contained additional defects, and the
smaller arm produced more low-value findings across the completed pairs.
The exact frozen revision above remains the replay input; current fixtures
include the verified repairs. Raw responses, blinded judgments, timing, and
fixture snapshots were retained locally under ignored
`docs/superpowers/reviews/2026-11-14-review-quality/`.

## Observed comparison, 2026-11-16

A second attempt stopped in its first group. Inputs and skill were frozen at
`8bd52a1c461e23c1f78f0aefc9d17cbc44e3f886`, with promotion settings
`0/false/false`. A Claude Code parent launched every reviewer through Witch as
a Codex `gpt-6.1-sol` session at high effort: read-only sandbox, approval
policy `never`, with MCP servers, apps, and plugins off.

All six inputs passed their command checks before dispatch. Cases 01, 03, and
05 failed on their seeded assertion; cases 02, 04, and 06 passed. Each passed
Ruff 0.15.13 and 0.16.0 in its exported repository. The same check at
`c84b044` found that cases 01 and 02 failed Ruff 0.16.0 outside this checkout's
configuration (`PLW1510` in `checks.py`); the frozen revision carries that fix.
Eleven concurrent preflight sessions then completed on the frozen model,
effort, sandbox, and approval policy, and each was denied a write.

Case 01's full panel ran next. Ten reviewers returned schema-valid responses.
The `performance` response failed validation: its `evidence.notes` was an
array where `reviewers/output.schema.json` requires a string. That pair is
incomplete. No reviewer was relaunched, the adversary did not run, no further
group was dispatched, and nothing was judged. This attempt has no finding
counts, seed retention, or arm comparison.

| Case 01, full panel | Value |
| --- | --- |
| Reviewer sessions | Eleven started and completed; ten valid responses |
| Panel elapsed | 107.7 seconds |
| Summed session time | 753.8 seconds |
| Dispatch to last response | 123.3 seconds |
| Total tokens | 1,681,455 |
| Input, of which cached | 1,656,406, of which 1,431,552 |
| Output, of which reasoning | 25,049, of which 5,403 |

Times run from each session's start to its `task_complete` in the native
trace; the 2026-11-14 figures used report-file times. Monetary cost is
unavailable for these sessions. The preflight used 398,698 tokens and is not a
reviewer invocation.

Every reviewer trace showed the frozen settings, no spawned session, and no
approval flow, and the reviewed checkout stayed clean. All eleven ran
`checks.py`; the host's default `python` is 3.11.4. None read the case table,
another case, or this checkout. Two read the host's own Codex `gh-pr-review` skill:
reviewers inherit the host's global Codex instructions and installed skills.

The result does not support a smaller-panel recommendation, since no pair
completed. Under the procedure one invalid response in any reviewer invocation
ends a run. The skill's own loop can ask a reviewer to resend malformed output;
this run's one-shot launches had no such step. Raw responses, traces, prompts,
helper scripts, and the reviewed run plan were retained locally under ignored
`docs/superpowers/reviews/2026-11-16-panel-comparison/`.

## Validation status

**Status:** `design_only`
**Evidence:** The 2026-11-14 comparison covers three complete pairs and records the incomplete fourth pair. The 2026-11-16 attempt records verified inputs and one incomplete pair.
**Missing evidence:** Complete clean controls and holdouts, plus the unused-validator and loud-failure checks, before claiming this whole scenario passed.
