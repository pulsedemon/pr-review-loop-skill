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

6. **Unused validator.** Repeat Check 1 with no production callers of the validator; only tests reference it. Run `type_design`. Expect a suggestion rather than a blocker, with `detail` giving the downgrade reason: the validator has no production caller. Any wording that states that reason passes. This exercises the reachability gate independently of the positive case.

7. **Loud validation failure.** Construct a separate validator fixture that exits nonzero or raises when validation fails, while its surrounding change has no handler or test for that failure. Run `blind_spots`. Expect category (b1), citing the unhandled failure. A finding on that same path must not classify it as a silent (b2) success. Reusing Check 2 would not exercise this distinction.

## Pass criterion

Compare each finding with the seeded behavior and its evidence, not just its severity or presence:

- Check 1 cites `templates/state.schema.json` and the missing `addressed` or `deferred` required fields.
- Check 2 cites the success result in `scripts/run_local_validation.sh` when the required tool is unavailable.
- Check 3 cites the unanchored-bucket contract and missing processing in the recall harness.
- Check 6 has `severity: suggestion` and a `detail` that gives the missing production caller as the reason for the downgrade, in any wording.
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
completed. Under the procedure at that time, one invalid reviewer response
ended a run. The skill's own loop can ask a reviewer to resend malformed output;
this run's one-shot launches had no such step. Raw responses, traces, prompts,
helper scripts, and the reviewed run plan were retained locally under ignored
`docs/superpowers/reviews/2026-11-16-panel-comparison/`.

## Observed rerun, 2026-11-16

All six pairs completed at frozen revision
`e71cbdd4a900f2fd59c8a886c2d30c7f52cb12de`, which amended the invalid-response
rule after the earlier attempt. The smaller override met the procedure's
decision rule: every seed remained a blocker in both arms, with lower token
usage and reviewer-phase time, no false blockers, and fewer low-value issues.
This supports `approvers_required=correctness,tests,security` for these bounded
fixtures. It does not establish equal recall: the full panel found five
additional useful issues across the cases. The default panel is unchanged.

The Codex parent used Witch-routed `gpt-6.1-sol`, high effort, for every panel
and adversary, with promotion settings `0/false/false`, a read-only sandbox,
approval policy `never`, and MCP servers, apps, and plugins off. Arm order
alternated by case. The full arm used the default eleven personas; the smaller
arm used the three named personas. Each received a fresh adversary with its
own panel's full responses. All 96 original responses validated. No replacement,
failed launch, timeout, route change, or promotion occurred. The replacement
rule was exercised in a helper replay, not by these reviewer sessions.

Before dispatch, Python 3.14.6 command checks failed at the intended seeds in
cases 01, 03, and 05 and passed in cases 02, 04, and 06. All exported cases
passed Ruff 0.15.13 and 0.16.0. Eleven simultaneous native preflight sessions
completed and were denied writes; a separate timeout probe stopped without
leaving a child process. The eleven preflight sessions used 401,688 tokens and
the timeout probe 55,018, all excluded from the comparison. Pilot judgments
were frozen before the holdouts ran.

### Findings

Counts are unique issues per case and arm after blinded judgment, not raw
findings. There were no false or unjudgeable issues in either arm.

| Case | Full: useful / low-value / false | Smaller: useful / low-value / false | Seed retained as blocker |
| --- | --- | --- | --- |
| 01, schema enforcement | 3 / 0 / 0 | 2 / 0 / 0 | Both arms |
| 02, corrected schema | 6 / 0 / 0 | 2 / 0 / 0 | No schema-seed finding |
| 03, unavailable checker | 1 / 1 / 0 | 1 / 0 / 0 | Both arms |
| 04, corrected checker | 0 / 1 / 0 | 0 / 1 / 0 | No checker-seed finding |
| 05, omitted buckets | 1 / 1 / 0 | 1 / 1 / 0 | Both arms |
| 06, corrected buckets | 0 / 1 / 0 | 0 / 1 / 0 | No bucket-seed finding |

Duplicate reports also placed the schema seed in suggestions in both arms and
the missing-checker seed in deferred findings in the full arm; each still had
a retained blocker. Unsupported blockers were separate from false findings:
the full arm had three record-structure coverage issues in case 02, and both
arms had command-entry-point coverage issues in cases 05 and 06. Greeting-test
suggestions in cases 03 and 04 were factual but low-value.

The full-arm `type_design` response cited the declared schema fields and
missing enforcement. `blind_spots` described success without running the
checker. `readability` identified the bucket mismatch as Move C contract drift;
`comments` returned no finding on that case.

The locations below are relative to each case under
`tests/fixtures/reviewer-quality/`, at the frozen revision. They cover every
adjudicated issue, combining repeated locations for the same behavior.

| Cases | Issue | Locations | Arms |
| --- | --- | --- | --- |
| 01 | Missing entry fields in schema | templates/state.schema.json:11,12,13,19,20 | Both |
| 01, 02 | Missing non-string cause check | checks.py:34 | Both in 01; full in 02 |
| 01, 02 | Uncaught parser recursion | app.py:16,18 | Full in 01; both in 02 |
| 02 | Invalid UTF-8 accepted | app.py:15 | Full |
| 02 | Missing required-array checks | checks.py:23,35 | Both |
| 02 | Missing root-object check | checks.py:35 | Full |
| 02 | Missing array-type check | checks.py:35 | Full |
| 03 | Missing checker returns success | scripts/validate.sh:6 | Both |
| 03, 04 | Missing greeting test | app.py:1 | Full in 03; both in 04 |
| 05 | Unanchored buckets omitted | docs/label.md:4; report.py:7 | Both |
| 05, 06 | Missing command-entry-point check | report.py:11,12 | Both |

The full arm alone found the recursion error in case 01 and invalid encoding,
non-string cause coverage, root-object coverage, and array-type coverage in
case 02. No useful issue appeared only in the smaller arm. The nominal schema
controls therefore still contained unseeded defects. Invalid UTF-8 was accepted
on Python 3.12.6 and 3.14.6; excessive nesting exited 1 on Python 3.12.6 instead
of the fixture's required 2. The latter already exited 2 on Python 3.14.6.
The fixtures advertise Python 3.12+, separately from the skill's Python 3.14
minimum. Both fixture copies now reject invalid UTF-8 and catch recursion
errors, with command regressions and the verified schema-coverage gaps added
after the freeze. Their intentional schema defect remains intact.

### Usage and timing

Times below are seconds from native session timestamps. Panel elapsed spans
the earliest panel start to the latest panel completion; reviewer-phase time
adds the adversary duration. Total elapsed runs from dispatch to adversary
completion and includes parent gaps. It excludes time between groups. Summed
session time adds concurrent sessions and is not wall time. The earlier
2026-11-14 record instead used report-file timestamps.

| Case | Arm | Tokens | Panel | Adversary | Reviewer phases | Summed sessions | Total elapsed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 01 | Full | 1,901,287 | 113.5 | 93.1 | 206.6 | 804.5 | 521.2 |
| 01 | Smaller | 697,994 | 94.1 | 77.7 | 171.8 | 303.1 | 200.5 |
| 02 | Full | 2,038,111 | 116.3 | 111.4 | 227.7 | 842.1 | 239.7 |
| 02 | Smaller | 832,399 | 117.2 | 76.7 | 193.9 | 375.0 | 207.6 |
| 03 | Full | 1,398,904 | 70.1 | 89.5 | 159.6 | 591.1 | 173.6 |
| 03 | Smaller | 548,457 | 81.7 | 37.2 | 118.9 | 222.9 | 128.3 |
| 04 | Full | 1,639,129 | 86.3 | 76.4 | 162.7 | 653.0 | 180.5 |
| 04 | Smaller | 528,171 | 80.3 | 50.8 | 131.1 | 255.7 | 141.8 |
| 05 | Full | 1,381,142 | 73.2 | 35.2 | 108.4 | 540.9 | 121.8 |
| 05 | Smaller | 511,992 | 54.3 | 60.8 | 115.1 | 192.1 | 133.1 |
| 06 | Full | 1,405,727 | 54.5 | 46.9 | 101.4 | 479.1 | 112.0 |
| 06 | Smaller | 497,786 | 42.8 | 49.0 | 91.9 | 168.9 | 112.1 |

| Six-pair total | Full | Smaller |
| --- | --- | --- |
| Sessions | 72 | 24 |
| Total tokens | 9,764,300 | 3,616,799 |
| Input, of which cached | 9,626,945; 8,249,216 cached | 3,562,314; 3,081,216 cached |
| Cache-write input | 0 | 0 |
| Output, of which reasoning | 137,355; 35,253 reasoning | 54,485; 14,384 reasoning |
| Reviewer-phase seconds | 966.4 | 822.7 |
| Summed-session seconds | 3,910.6 | 1,517.8 |
| Total elapsed seconds, summed by group | 1,348.7 | 923.5 |

The smaller arm used 63.0% fewer total tokens and 14.9% less reviewer-phase
time. Cached input and reasoning output are subsets, not additions to total
tokens. Monetary cost is unavailable. With no invalid responses, inclusive and
invalid-excluded usage are identical, and replacement gaps are zero. The
larger arm has more sessions eligible for replacement, whose costs would count
against that arm.

### Judgment and limits

Fresh Codex `gpt-6.1-sol` and Claude `claude-opus-5-5` judges independently
classified each batch with arm and reviewer identifiers removed. All judge
outputs and access audits passed; none was replaced. They agreed on label,
seed, and blocker-support sets for 36 of 37 pilot rows and all eleven holdout
rows. The parent retained the first judge's keys and values after checking
all rows against the frozen code and reproducing command failures. The one
label disagreement was invalid UTF-8: reproduction supported useful and
blocking, rather than low-value and unsupported. The first judge split
record-structure coverage into three issues; the second grouped it as one.

The pilot gate and final recommendation also pass under either judge's own
keys and labels and when unsupported blockers count as false blockers. The
second judge counts five full-arm low-value issues instead of four; the
smaller arm remains at three. Two pilot rows needed persona-name redaction;
none retained full-panel category tags. Holdout rows needed neither.

The usage tables cover reviewer and adversary sessions only; planning,
preflight, judging, and parent usage are excluded.

This is one pass per cell on synthetic inputs, with one reviewer model and
effort, not a general recall or speed estimate. The judging Codex model was
also the reviewing model. The dispatching parent adjudicated knowing the arm
schedule, and knew pilot results when judging holdouts. Before the rerun it
had seen an approval note from the earlier failed attempt. It did not read
this run's arm map or raw findings until each batch's judgments were frozen.
Planning began under Claude Code; execution resumed under Codex before any
rerun reviewer was launched.

Native traces showed no spawned reviewer sessions, approved escalations, or
reads of another case, the other arm's responses, or this checkout. Some
reviewers read the host's own Codex `gh-pr-review` instructions. Read-only
restrictions prevented temporary-file probes and some heredocs; reviewers
could run inline command probes. Their default Python was 3.11.4, while the
parent verified the host/helper path on 3.14.6 and the fixture's recursion
behavior on its advertised 3.12.6. Those are distinct sources of evidence.

The first group's collector initially read wrapper progress text as part of
the response. It was corrected to use the native final answer, agreeing with
the native completion message, and reprocessed the same sessions. This caused
the large case-01 full-arm parent gap; it changed no reviewer input and
resampled nothing. Summary fixes retained completed zero-finding pairs and
selected only validated judge outputs. Generated bytecode after pilot
blinding was removed before holdout dispatch; all frozen source hashes
matched. These helper corrections and their checks are retained with the
run, alongside raw responses, traces, prompts, frozen inputs, judgments,
and the reviewed plan, under ignored
`docs/superpowers/reviews/2026-11-16-panel-comparison-rerun/`.

## Observed checks 6 and 7, 2026-11-16

Fixtures and persona prompts were pinned at
`cacdb03215ba5db7be2f876aa5d7bc319d327e83`.
[Case 07](../fixtures/reviewer-quality/case-07/README.md) carries case 01's
schema defect with only a test consumer. Check 6 ran `type_design` on it.
[Case 08](../fixtures/reviewer-quality/case-08/README.md) handles every
invalid record with exit 2, except a missing `addressed` or `deferred` array,
which raises an uncaught `KeyError` and exits 1. Check 7 ran `blind_spots` on
it. Each check ran once on each Witch-routed runtime: Codex `gpt-6.1-sol` at
high effort, and Claude `claude-opus-5-5` at high effort.

Before dispatch, the pinned export was checked on Python 3.14.6, 3.12.6, and
the reviewers' default 3.11.4. Case 07's check failed at its item-field
assertion, and the schema accepted `{"addressed":[{}],"deferred":[]}`. Only the
test and README referenced the schema or `jsonschema`. Case 08's checks passed,
and each missing-array input exited 1 with a `KeyError` and no stdout. Both
cases passed Ruff 0.15.13 and 0.16.0.

Each session reviewed its own copy of the case, with an empty base commit and a
head commit adding the case. The skill export held only the two persona
prompts, their addenda, `reviewers/output.schema.json`, and
`docs/procedure-moves.md`. The rest of the skill names
`templates/state.schema.json` as its own production schema and would have
supplied case 07 with consumers. Codex sessions ran read-only, with approval
policy `never` and MCP servers, apps, and plugins off. Claude sessions ran in
`--restricted` `dontAsk` mode. They had file tools confined to the case and the
skill export, plus Bash limited to `git diff`, `git show`, `git log`,
`git status`, and the case's check command. A preflight
session confirmed that writes, `gh`, `git --output`, ad hoc `python -c`, and
reads of this checkout were denied, and that read-only `ls` and `cat` inside
the case were allowed.

| Check | Runtime | Disposition | Result |
| --- | --- | --- | --- |
| 6, `type_design` | Codex | suggestion on `templates/state.schema.json:12`, detail ending "validator unused in production" | Pass |
| 6, `type_design` | Claude | suggestion on `templates/state.schema.json:12`, detail stating "the validator is unused in production: no non-test caller exists" | Pass under the amended criterion; failed the literal one in force at the run |
| 7, `blind_spots` | Codex | (b1) suggestion on `app.py:23`, citing the `KeyError` and exit 1 | Pass |
| 7, `blind_spots` | Claude | (b1) blocker on `app.py:23`, citing the `KeyError`, traceback, and exit 1, and stating "this is (b1) and not (b2)" | Pass |

Each session returned one finding, on the seeded defect, and its response
passed schema validation without replacement. Both `type_design` sessions
searched the whole case for schema consumers before downgrading: Codex with
`rg` for `state.schema`, `jsonschema`, and the validator class, and Claude with
Grep for `state\.schema|addressed|deferred`. Each found only the test. Claude's
check 6 detail gives the downgrade reason in different words. The Claude
check 7 blocker acknowledges that the persona's (b1) blocker bar of state
corruption or a resource leak is not met, and escalates on the README's
exit-code contract instead.

When these sessions ran, Check 6 required the literal phrase "validator unused
in production" in `detail`. The Claude session's `detail` missed it on wording
alone; its `evidence.notes` carried the phrase verbatim. The criterion was
amended afterwards
([issue #23](https://github.com/pulsedemon/pr-review-loop-skill/issues/23)) to
accept the reason in any wording. `reviewers/type_design.md` tells the reviewer
to note the reason without requiring the phrase in `detail`, no script reads
`detail` for it, and `tests/bats/test_type_design_gate_text.bats` checks the
persona's own text, not reviewer output. The persona is unchanged since the
pin, so the Claude result above was re-judged from its retained response, not
rerun.

All four sessions passed the access audit. Each trace showed the launched model,
effort, and permission settings. No session spawned another or used the
network, and none read outside its case and the skill export. No transcript
input carried the case table, this scenario, the issues, or another session's
output, and every case copy kept its hashes and a clean status. The Claude
sessions' compound commands outside the allowlist were denied, so neither ran
its check command. Their failure claims come from reading the code, as their
notes state. The Codex sessions ran their checks and ad hoc probes.

This is one pass per runtime on synthetic inputs. The dispatching parent wrote
the fixtures and judged knowing the expected answers. Each finding was checked
against the pinned code and the command results above. Prompts, raw responses,
native traces, the preflight, and helper scripts are retained under ignored
`docs/superpowers/reviews/2026-11-16-scenario-25-checks-6-7/`.

## Observed check 5, 2026-11-16

Fixture, persona prompts, and skill export were pinned at
`9e63f9d1251c6b1593a88449af0a188aa834030d`. The default panel reviewed
[case 06](../fixtures/reviewer-quality/case-06/README.md) once. Every persona
returned `verdict: approve` with `findings: []`, so Check 5 is met as written.

Case 06 was named as the deciding fixture before any session ran: it is the
smallest control, and its one known gap could be repaired without touching
another scenario's inputs. In the rerun above its `checks.py` imported `render`
and never ran the documented `python report.py` command, which
`reviewers/tests.md` counts as an entry point. The pin adds that command run to
`checks.py` in cases 05 and 06, which still differ only at `report.py:7`. A copy
of case 06 whose `__main__` block no longer calls `render` passed the old checks
and fails the new assertion. The rerun's judgments and counts are not
relabelled, and `e71cbdd` remains the replay input for the paired comparison.

Case 04 was not used. Its untested `greeting` is a nit whenever `tests` raises
it, and removing the gap would change the inputs
[scenario 30](30-tests-coverage-calibration.md) records as "case-04 as shipped".
Case 02 was not rerun, so its repairs since the rerun have had no panel pass.

Before dispatch, on an export of the pin, case 06's `checks.py` passed and case
05's failed at its seeded assertion on Python 3.14.6 and on the reviewers'
default 3.11.4. Both cases passed Ruff 0.15.13 and 0.16.0. The skill export was
byte-identical to the pins of Checks 1 to 3 (`e71cbdd`) and Checks 6 and 7
(`cacdb03`). One preflight session on the same settings had its write refused.

A Claude Code parent launched every reviewer together through Witch as a Codex
`gpt-6.1-sol` session at high effort (Codex CLI 0.162.1): read-only sandbox,
approval policy `never`, with MCP servers, apps, and plugins off. Each session
started in a repository holding an empty base commit and one head commit adding
case 06, beside the skill export, and received the rerun's prompt template
unchanged. Outcome rules, audit failure conditions, and a single permitted
fixture-repair round were fixed in a reviewed plan before dispatch; the repair
round was not needed.

| Persona | Verdict | Findings |
| --- | --- | --- |
| `correctness` | approve | none |
| `tests` | approve | none |
| `security` | approve | none |
| `performance` | approve | none |
| `readability` | approve | none |
| `yagni` | approve | none |
| `requirements` | approve | none |
| `comments` | approve | none |
| `error_handling` | approve | none |
| `type_design` | approve | none |
| `blind_spots` | approve | none |

Every response was read from its native final answer, matched the native
completion message, and passed `validate_reviewer_output.py` without
replacement. No launch failed or timed out.

| Measure | Value |
| --- | --- |
| Panel elapsed | 57.4 seconds |
| Summed session time | 436.3 seconds |
| Total tokens | 1,172,257 |
| Input, of which cached | 1,160,070, of which 914,304 |
| Output, of which reasoning | 12,187, of which 1,437 |

Times come from native session timestamps. Monetary cost is unavailable. The
preflight used 36,945 tokens and is not a reviewer invocation.

The access audit passed. Every turn showed the launched model, effort, sandbox,
and approval policy. No session spawned another, raised an approval flow, used
the network, or ran a command that read outside its repository and the skill
export. Every session ran `python -B checks.py`; three also probed `report.py`
with their own inputs. Two heredoc probes were refused by the sandbox and rerun
inline. The repository stayed clean and every frozen file, prompt, and helper
hash matched after the run. The parent read every command; output lines that
were not lines of a file in the reviewer's packet were read in full, and the
rest were matched to those files by program.

Each session also received the host's global Codex instructions and skill
list. That list names this checkout's installed skill link, including the
skill copies kept in earlier retained run directories. No session read through
it. The list carried no case table, scenario text, expected answer, or other
reviewer's output.

| Check | Recorded in | Pin | Input |
| --- | --- | --- | --- |
| 1 | Observed rerun, 2026-11-16 | `e71cbdd` | Case 01, the path the check names |
| 2 | Observed rerun, 2026-11-16 | `e71cbdd` | Case 03, a stand-in |
| 3 | Observed rerun, 2026-11-16 | `e71cbdd` | Case 05 before this pin's change to its `checks.py`, a stand-in |
| 4 | `tests/bats/validate_reviewer_output.bats` | current | Automated |
| 5 | This section | `9e63f9d` | Case 06 |
| 6 | Observed checks 6 and 7, 2026-11-16 | `cacdb03` | Case 07 |
| 7 | Observed checks 6 and 7, 2026-11-16 | `cacdb03` | Case 08 |

Checks 2 and 3 have not run on the constructions they name. Check 2 specifies
`scripts/run_local_validation.sh` with a detected stack whose package manager
is unavailable; case 03's `scripts/validate.sh` has a missing-tool branch that
checks for Ruff. The retained `blind_spots` response cites that branch's exit 0
without printing the (b2) label, and the output schema has no field for it.
Check 3 specifies `tools/recall-harness/report.py` and `label.md`; case 05 uses
its own `report.py` and `docs/label.md`. Check 6 was held to its literal
wording until it was amended, and the same standard keeps this scenario at
`design_only`.

This is one pass on one synthetic fixture, with one reviewer model, effort, and
runtime. Case 06 is not held out: it was repaired in response to the same
reviewer setup's earlier finding, and the dispatching parent wrote the repair
and judged the result knowing the expected answer. The rerun was dispatched
from a Codex parent on a different Witch route, and stripped Markdown fences
before validation where this run sent each final answer to the validator
unchanged. Plan, plan reviews, prompts, raw responses, native traces, audit
output, and helper scripts are retained under ignored
`docs/superpowers/reviews/2026-11-16-scenario-25-check-5/`.

## Validation status

**Status:** `design_only`
**Evidence:** The dated observations above retain both incomplete comparison attempts, the completed six-pair rerun with blinded judgments, native usage, and limits, single-pass runs of Checks 6 and 7 on both runtimes, and a clean default-panel pass on case 06 for Check 5.
**Missing evidence:** Checks 2 and 3 have been observed only on stand-in fixtures (cases 03 and 05), not on the constructions those checks name.
