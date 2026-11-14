# Scenario 29: YAGNI responsibility

**Type:** Manual comparison of YAGNI persona revisions using isolated PR fixtures.

## Setup

Freeze the old and revised persona, its linked addenda, and the output schema.
Create four small TypeScript Git fixtures and two sibling-context variants of
the first fixture. Retain each base/head revision, source tree, diff, PR body,
and check command. Keep expected review dispositions outside reviewer context.

| Case | Fixture | Expected revised response |
| --- | --- | --- |
| 01 | A single `DeliveryBatchAdapter` groups trimmed bodies by normalized recipient, drains its state, and serves one production caller across two batches. | Preserve its conversion, grouping, and state responsibility without a count-based finding. |
| 02 | `collectPresent<T, U>` projects items, removes only `null`, and returns `U[]`; its one production caller projects numeric scores. | Preserve the generic's input/callback/result relationship without a count-based finding. |
| 03 | `formatName` accepts a new `verbose` parameter and a caller passes it, but its body never reads or forwards it. | Identify the unread parameter as a blocker. |
| 04 | A new `displayName` wrapper forwards both arguments and the result of `renderName` unchanged, without another responsibility. | Identify the redundant wrapper as a blocker. |
| 05 | Case 01 has no local production caller; its PR body references a separately supplied sibling source snapshot containing the caller. | Inspect that snapshot before judging use and preserve the useful adapter. |
| 06 | The same sibling reference exists, but its source is unavailable. | Record missing evidence and avoid claiming the adapter is unused. |

Check fixture behavior before dispatch. Case 01 must normalize recipient ids,
preserve insertion order, clear drained state, and leave an earlier result
unchanged after a later batch. Case 02 must return `[0,7]` for scores
`0` (included), `3` (excluded), and `7` (included). Compile a `number[]`
consumer and an expected error for a `string[]` consumer using the actual
inferred return type. Runtime checks alone do not establish that relationship.
For cases 03 and 04, inspect full bodies and callers as well as verifying
the exact formatter results. Keep unrelated fixture behavior valid.

## Comparison procedure

Run one fresh YAGNI reviewer per case and prompt revision, twelve scheduled
responses total. Keep the model, effort, fixture bytes, permissions, and prompt
format constant. Supply only the selected case's PR metadata, diff, source,
persona, addenda, and schema. Withhold expected dispositions, the issue that
motivated the change, the alternate prompt, and other reviewers' responses.

Validate each response with `uv run python scripts/validate_reviewer_output.py <response.json> --reviewer yagni`.
Retain raw responses and native traces. Judge each finding against the
frozen source using the [labeling protocol](../../tools/recall-harness/label.md),
recording unsupported blocker classifications separately. Inspect traces for
caller and sibling reads; the evidence field alone is not proof of inspection.

A changed route, missing response, or invalid output makes the corresponding
comparison incomplete. Preserve it rather than replacing it silently. Record
any corrective evaluation as a separate run. A clean baseline still permits
correcting the written policy, but does not establish a measured improvement.

## Pass criteria

All six revised responses meet the table's expectations and pass schema
validation. Cases 03 and 04 must retain blockers, not just suggestions.
Count-only requests demoted to suggestions still fail cases 01 and 02.
Case 05 requires a recorded sibling-source read; case 06 requires an explicit
missing-context note without an unsupported unused finding.

These supplied sibling snapshots do not verify live GitHub fetching or the
full protocol in [scenario 12](12-yagni-sibling-pr.md). This bounded comparison
does not establish a false-positive rate, other hosts' orchestration behavior,
or full-panel quality. Structural wording checks cannot establish these
reviewer decisions.

## Observed comparison, 2026-11-14

Twelve fresh Codex `gpt-6.1-sol` sessions at high effort completed the comparison.
Each ran read-only with MCP disabled. Witch supplied the route. Both arms used
the same fixture bytes, dispatch text, addenda, and output schema. Native review
sessions could also load the installed `gh-pr-review` inspection skill; these
results apply to that environment, not to a persona-only model invocation.

The baseline was `reviewers/yagni.md` at
`fa824c4216b706eb45a18b8daac77090778dcefa`, SHA-256
`1d3e4cd478cca828fd9002817a8e8fb48860989a27dc934005f142ff26c7d464`.
The revised prompt's SHA-256 was
`d1a3c580e056e515e113d75eae162b38bfbbd0e7eb2c20741a3871b0244e3c42`.

| Case | Fixture head | Baseline | Revised |
| --- | --- | --- | --- |
| 01 | `9728dbf43c66d9e2d8d48ce1fbc5b5e791d0fbf6` | Approve, no findings | Approve, no findings |
| 02 | `0ed155234e717dd4a5f62dd7cd1c34df78232274` | Approve, no findings | Approve, no findings |
| 03 | `0f5b5bf83518c045e58c2ec4b9bd6f721b8be522` | Unread-parameter blocker | Unread-parameter blocker |
| 04 | `13bef0d939cbc9f41c4fd1f8d5c0cbe191d65c3f` | Redundant-wrapper blocker | Redundant-wrapper blocker |
| 05 | `74666af0888d8f442839342cf427cd098ac1021b` | Approve after sibling inspection | Approve after sibling inspection |
| 06 | `74666af0888d8f442839342cf427cd098ac1021b` | Approve with missing-context note | Approve with missing-context note |

Each arm produced two useful findings, zero low-value or false findings, and
zero unsupported blockers. All twelve exact final responses passed the existing
JSON validator. Native traces show the caller searches and sibling-source reads;
the missing-sibling responses explicitly preserved that uncertainty. The fixture
checkouts remained unchanged.

Before dispatch, TypeScript 5.8.3 compiled all six fixtures with `--strict` and
`--noEmitOnError`; their Node checks passed. The supplied sibling consumer also
compiled with the producer and returned the independently expected batches.
The generic fixture checked its inferred numeric result and rejected a string
array assignment. Cases 05 and 06 share code and head hashes; their supplied
sibling metadata differs.

The baseline already met every target disposition. This run verifies the revised
policy on these cases and retention of the two intended catches; it does not
demonstrate a behavioral improvement. Raw reports, exact final JSON, native
traces, fixture repositories, dispatch packets, hashes, and judgments are retained
locally in ignored `docs/superpowers/reviews/2026-11-14-yagni-responsibility/`.

_Validated with Codex `gpt-6.1-sol`, high effort, on the prompt hashes above: PASS._

### Corrective run, 2026-11-14

The structural checks then detected that the prompt edit had removed the
explicit cap condition on forced adversary runs after a shallow review. The
condition was restored without changing the test or YAGNI severity rules.
The final prompt's SHA-256 is
`28becca98b3cf371db730e86711cfc9b4cb354cd125dfd21eed66863595611fe`.

Six additional fresh sessions used the same model, effort, fixtures, and
dispatch text. All six returned the same dispositions as the revised column
above and passed schema validation. The two seeded blockers remained useful;
no low-value findings, false findings, or unsupported blockers were observed.
Native traces again record caller/sibling inspection and the missing-context
note. This separate corrective run retains its own `corrected-*` reports and
traces alongside the original twelve responses.

_Validated with Codex `gpt-6.1-sol`, high effort, on the final prompt hash above: PASS._

## Validation status

**Status:** `manual_validated`
**Evidence:** The dated comparison and separate corrective run above record all six final-prompt responses and preserve their baseline and earlier revised counterparts on frozen inputs.
