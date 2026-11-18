# Scenario 26: parallel reviewer fan-out stays batched

**Type:** Manual orchestration regression check.

## Setup

Use any non-trivial PR (real or fixture) that causes the loop to run:

- at least one normal §4b reviewer pass with multiple personas in scope; and
- if possible, one §4a.1 delta-gate pre-pass with multiple candidates.

Run the loop from a host that supports parallel subagent spawning and exposes a
visible subagent/task timeline. Repeat at least one run with
`subagent_model_profile=cost_saver`.

## Checks

1. **Reviewer fan-out is batched.** On a §4b pass with multiple personas in
   `panel_selection.ran`, the host shows one parallel launch containing the
   whole reviewer set. It does **not** show the orchestrator launching
   `correctness`, then `tests`, then `security`, etc. one at a time in
   separate tool calls/messages.

2. **Delta-gate fan-out is batched.** On a §4a.1 pass with multiple gate
   candidates, the host shows one parallel launch for the gate subagents. It
   does **not** serialize gate reviewers one-by-one when parallel spawning is
   available.

3. **Sequential fallback remains conditional.** If you repeat the run in a host
   without parallel subagent support, sequential launches are acceptable, but
   the outputs must still stay independent until synthesis (reviewers) or
   validation/selection (delta-gate).

4. **No semantic drift.** Batched launches do not change who runs: the
   personas visible in the host timeline still match `panel_selection.ran` for
   §4b and the gate-candidate set for §4a.1.

5. **Model routing does not break batching.** With
   `subagent_model_profile=cost_saver`, both the §4a.1 delta-gate fan-out and
   the §4b reviewer fan-out still launch as one parallel batch each, even though
   every reviewer subagent is spawned on a cheaper tier than the adversary.

## Pass criterion

All applicable fan-outs are launched as a single parallel batch whenever the
host supports that capability; sequential dispatch appears only on hosts that
lack parallel subagent spawning. Per-phase model routing changes which model
each subagent uses but never splits a fan-out into serial launches.

## Notes

Run this scenario manually after any change to `SKILL.md`, `AGENTS.md`,
`docs/delta-gate.md`, or any orchestration guidance that could affect how hosts
launch reviewer or gate subagents.

## Manual runs

- The [2026-11-14 live GitHub run](27-comment-reply-disposition.md#live-github-approval-path-2026-11-14) also launched the full panel in one batch, then a separate adversary; it did not exercise delta gates or `cost_saver`.

- Date: 2026-11-14
- Host: Codex through Witch, prompts frozen at `90e5593`
- Target: [Scenario 25's paired fixtures](25-persona-recall-sharpening.md#observed-comparison-2026-11-14)
- Reviewer fan-out: observed as one batch per arm, with one native launch per persona and results awaited after all launches.
- Delta-gate fan-out: not observed; the [fresh host fixture](24-adversary-full-default.md#changed-default-fixture-run-2026-11-14) used injected gate receipts.
- Limits: `cost_saver` and a host without parallel support were not exercised; one later panel was incomplete after registration and native approval-review failures.

- Date: 2026-10-28
- Host: Claude Code, skill read through its install symlink from the branch of
  PR #157
- Target: the original private repository (`dry_run=true`); the PR URL is omitted.
- Reviewer fan-out: PASS
- Delta-gate fan-out: NOT OBSERVED
- Notes:
  - Every §4b reviewer launch and the reviewer-budget timer (a background
    `sleep 1800`) went out in a single message, and the personas launched
    matched `panel_selection.ran` (check 4).
  - Every reviewer returned a validated response before the budget, and the
    timer was then stopped with `TaskStop`.
  - The orchestrator was the session that wrote the budget recipe, so the run
    shows the mechanics hold in a real loop, not that a fresh orchestrator
    follows the prose.
  - Delta-gate batching (check 2) and `cost_saver` (check 5) were not run.

- Date: 2026-09-10
- Host: Claude Code, skill installed from a local merge of PR #141 and PR #142
- Target: a separate repository (`dry_run=true allow_draft=true`); the private PR URL is omitted.
- Reviewer fan-out: PASS
- Delta-gate fan-out: NOT OBSERVED
- Notes:
  - All 11 §4b reviewer launches were issued in a single message and awaited
    after the last launch; the personas launched matched `panel_selection.ran`
    (check 4). The orchestrator recorded its own dispatch; the host task
    timeline is the external evidence.
  - Delta-gate batching (check 2) could not be observed: a dry run stops after
    iteration 1, before §4a.1 ever runs.
  - The `cost_saver` variant (check 5) was not run.
  - Every helper resolved through `$SKILL_ROOT` on a repo that is not the
    skill, the first run that exercised that path.

## Live multi-iteration Codex run, 2026-11-15

A fresh Codex parent ran the skill pinned at
`cdc395d6dae7fc15a5f2465a25f2ad0e44f9a21a`. Witch launched the parent and every
reviewer through a dedicated build of
[Witch commit `29839d7`](https://github.com/pulsedemon/witch/commit/29839d75d986bf2cec1953753c17a9c939179260), which
repairs nested familiar registration. The earlier attempt stopped before any
reviewer returned; its unchanged fixtures and `REVIEW_INCOMPLETE` records were
retained separately. No skill helper or persona changed between attempts.

The parent used `gpt-6.1-sol`, `subagent_model_profile=inherit`, the default
11-persona panel and promotion settings, `delta_gate=true`, and
`max_iterations=4`. It ran with native workspace-write permissions; reviewers,
gates and the adversary were read-only. Native approvals remained in force.
Read-only restrictions prevented mutation probes, and the parent's sandbox
refused process inspection. Some gates loaded ambient native skill instructions;
no installed loop helper or persona replaced the pin. Those limits are recorded
in the evidence.

Git used real commits and independent local bare remotes, with file transport
only. A traced adapter supplied GitHub metadata and empty discussions, reported
no CI checks, and captured the final summary locally. These are injected
services, not live GitHub or CI evidence. Reviewer and gate decisions were real;
only the failure case's delivered `tests` verdict was deliberately corrupted.

| Stage | Observed result |
| --- | --- |
| Initial review | The full panel launched as one batch. Actual findings identified incorrect shipping at the documented 5000-cent boundary. |
| Repair and push | The parent reproduced the CLI defect, verified the repair before adding its regression, checked that regression against the seed, and passed the local validation helper. One repair commit moved local and remote heads from `e80393822d54c4cf9556fc8cbd2a5a1a1b8438f5` to `39ca88aa263bde74dd45cbe33c1d5f37f45e6ed0`. |
| Delta gates | Eight actual gates launched as one batch and returned validated `relevant: false`. Blocker carryover selected `correctness`, `tests`, and `requirements`; there were no fail-open selections. |
| Forced sweep | The three-persona pass found no blockers. The full panel then ran again in iteration 2, with `forced_full_sweep: true` and complete validated receipts. |
| Approval | A fresh adversary received all raw sweep responses and approved. The completion helper checked fresh comments and matching heads; state and terminal metrics recorded `SUCCESS` in iteration 2. One summary was captured locally. |
| Required-review failure | A separate fresh fixture ran the actual full panel. The parent changed only the delivered `tests` verdict from `request_changes` to invalid `approved`, retaining the raw response. Validation failed; history retained two other genuine findings and the error, then recorded `REVIEW_INCOMPLETE`. Tracked bytes, head `6946386653592afad4149d8403a7bbbc5d322ba9`, and all remote refs stayed unchanged. No GitHub adapter call followed the injection. |

| Scenario 26 check | Result |
| --- | --- |
| 1. Reviewer batching | Passed for the initial panels, selected panel, and forced sweep. |
| 2. Delta-gate batching | Passed with eight actual gate launches. |
| 3. Sequential fallback | Not run; this host supports parallel launches. |
| 4. Persona selection | Passed; dispatch lists match selection and the full-sweep override. |
| 5. `cost_saver` routing | Not run; every phase used `inherit`. |

For Scenario 24, check 5's persisted outcomes and metrics were observed. Check
1's default full-object delivery was observed with empty findings; its
nonempty-findings condition was not exercised. Checks 2 through 4's invalid or
shallow adversary and last-iteration cases were not run. No additional complete
check among Scenario 27's checks 1 through 11 was established; this was its
empty-discussion completion path only.

Terminal metrics recorded 1,135 seconds for success and 315 seconds for
the failure case; they overlapped and exclude parent setup and reporting. All
45 child sessions completed. Their native counters total 7,578,514 tokens,
including 6,077,824 cached input tokens; these are child-session counters, not
billed cost or whole-task usage. Billed cost was unavailable. Per-dispatch
counters, native traces, source hashes, prompts, raw and delivered responses,
helper input/output, state, Git snapshots and root audits are retained locally
under ignored `docs/superpowers/reviews/2026-11-15-live-codex-loop/`.

This run establishes the multi-iteration path with a local Git remote and bounded invalid
required-review routing. It does not establish reviewer timeout cancellation,
`cost_saver`, sequential-host fallback, live GitHub/CI, inline replies, or a
Claude parent. The full sweep's findings were empty, so the adversary dispatch
establishes full-object delivery without testing retention of nonempty findings.

## Live GitHub dry run in Claude Code, 2026-11-17

A fresh Claude Code 2.1.322 parent ran `Dry-run pr-review-loop on <PR URL>`
against [PR #39](https://github.com/pulsedemon/pr-review-loop-skill/pull/39), a
fixture PR in this repository that was closed unmerged afterwards. Witch
launched the parent headless on `claude-opus-5-5`; the trace shows high effort
and the `auto` permission mode with no prompt handler. The request held the
invocation line and reporting instructions, and said nothing about batching,
the budget or models. The parent loaded the skill with its `Skill` tool and
resolved `SKILL_ROOT` to the install symlink, `~/.claude/skills/pr-review-loop`,
which pointed at a checkout of `dfc878d9a05b3f2db50b4d389de6164374428d9c`.
Startup sync was skipped with `PR_REVIEW_LOOP_SKIP_SKILL_SYNC=1`. Every loop
input other than `dry_run` kept its default. `python3` resolved to 3.14.6 in
all 42 Bash calls, the parent's and the reviewers'.

The fixture added a 25-line pricing module whose discount excluded the
documented 10-unit boundary, with tests that missed it. The run used the real
`gh` and Git against GitHub from a fresh clone.

| Observation | Result |
| --- | --- |
| Terminal state | `dry_run_complete` after one iteration: `ci_status` `skipped`, equal head SHAs at the fixture head, the full panel in `reviewers_completed`, empty `reviewer_errors` |
| Dispatch | Every panel persona had an `Agent` call joined to its own subagent transcript by the launch id |
| Model routing | Each reviewer call passed `model: sonnet` and each transcript ran on `claude-sonnet-5-5`; state recorded `reviewer` as `standard` / `sonnet` |
| Validation | `correctness` first returned an extra top-level field and failed validation; the parent asked for a resend, which passed 122 seconds after launch. Three other reviewers were asked to resend with file line numbers. State kept no error entry for the recovered response, and no `shallow_review` field |
| Findings | Six blockers and two suggestions on the seeded boundary defect, one deferred finding. The matcher merged none of them |
| GitHub and Git | PR metadata, comments, reviews, review threads and remote refs were identical before and after. No command in the parent or any reviewer wrote to GitHub or pushed, and none was denied. The host clone ended on the fixture branch at its head with a clean tree |
| Install checkout | `HEAD`, branch, status, stashes and tracked-file bytes of the checkout behind the install symlink were unchanged |

| Scenario 26 check | Result |
| --- | --- |
| 1. Reviewer batching | Passed: one message held the launch of every persona in `panel_selection.ran` and the budget timer. |
| 2. Delta-gate batching | Not run; a dry run ends in iteration 1. |
| 3. Sequential fallback | Not run; this host supports parallel launches. |
| 4. Persona selection | Passed: the personas launched matched `panel_selection.ran` and `reviewers/personas.yaml`. |
| 5. `cost_saver` routing | Not run; the profile was the default `balanced`. |

Budget recipe: reviewers were left in the background, and the launch message
started `date +%s > <file>; sleep 1800` in the background with `timeout`
1860000. The parent stopped the timer in the same message that validated the
last two resent responses, before those results came back, where the recipe
stops it once every reviewer has a validated response. Both validations
passed. The run therefore does not count as independent adherence to the
recipe. The budget did not expire.

The session lasted 284 seconds; the loop's terminal metric recorded 244. Native
counters total 2,798,180 tokens for the parent and 1,451,061 for the reviewers,
most of them cached input. Claude Code estimated USD 3.45 at API rates; billed
cost was unavailable. The request, launch settings, native traces, state,
snapshots, checkout observations and the trace audit are retained locally under
ignored `docs/superpowers/reviews/2026-11-17-claude-live-dry-run/`.

This run establishes that a Claude Code parent following the installed skill
dispatches the full panel as one batch on the routed model, validates the
responses and completes a dry run against a live GitHub PR without writing to
it. It does not establish the adversary, delta gates, `cost_saver`, the edit
and push path, CI handling, inline replies, summary posting, budget expiration,
permission prompts in an interactive session, or review quality. The target
repository was the skill itself, so the host's working directory held this
repository's `CLAUDE.md`, its scenario records and a root `SKILL.md`; no tool
call in the parent or a reviewer read a scenario record or retained evidence.
The session also carried the user's ambient Claude Code configuration.

## Live GitHub edit-path run in Claude Code, 2026-11-17

A fresh Claude Code 2.1.322 parent ran
`Run pr-review-loop on <PR URL> with max_iterations=5` against
[fixture PR #42](https://github.com/pulsedemon/pr-review-loop-skill/pull/42),
with the installed skill pinned at
`41cbb016184e9be1f0819c94e81265a7f31a5d3f`. Witch launched the parent headless
on `claude-opus-5-5`, with high effort and the user's ambient `auto`
permission mode. Inputs other than `max_iterations` kept their defaults,
including `balanced` model routing. Startup sync was disabled, and
`CLAUDE_ENV_FILE` put the repository's Python 3.14.6 environment first on PATH.

The launch used `--permission-prompts none` and `--strict-mcp-config`.
Explicit Bash allow rules covered `safe_push.sh`, `reply_pr_comments.sh`,
`gh pr comment`, `gh api`, `git add` and `git commit`. Disallowed tools were
`Workflow`, `WebFetch`, `WebSearch`, PR merge/close/edit/review commands, issue
create/comment/edit/close commands, and `git push --force` / `git push -f`.
A separate permission probe successfully pushed an empty commit through
`safe_push.sh` and posted through both GitHub comment commands; its two
comments were deleted before the run. The request required stopping at a
permission denial instead of working around it. The complete arguments and
request are retained with the evidence.

The fixture head was `122b38c58e969584b414e76174f1bb0332b5b0ff`. Its pricing
module excluded the documented 10-unit discount boundary; its two tests
covered quantities 5 and 11. An extra blank line in its README made the
`markdown` check fail with MD012 while the other nine checks passed. Two
inline threads from the PR author's account supplied a true boundary report
and a false claim that multiplying by 90% takes 90% off.

The host recorded `success` after three iterations and two repair commits:
`559ced1` fixed the boundary and added its test; `1b6f435` removed the extra
blank line. The final head was
`1b6f43528a54ad98b2af3d4ecb28b39080b0c85e`. The following results use the
rules fixed before launch. A recorded terminal status is distinct from
passing the audit.

| Rule | Result and evidence |
| --- | --- |
| E1. Terminal and completion gate | Passed. Three history entries, `completed_at` set, and a final no-commit entry with green CI, eleven validated panel responses, a validated adversary and no blockers. After append, fresh comments and matching local/remote heads produced `terminal_status: null`, `continue_full_panel: false`. |
| E2. Commits | Passed. Two single-parent repair commits matched the two changing entries and formed a continuous chain from the fixture head. Both messages followed the commit template. No prohibited Git operation executed. |
| E3. Pushes | Passed. Two successful `safe_push.sh` calls used the fixture branch and the preceding remote heads. No reviewer pushed. |
| E4. Fix and regression | Passed. Independent checks at a unit price of 100 returned 500, 900, 900 and 990 for quantities 5, 9, 10 and 11. All three final tests passed; the new threshold test failed against the seed with 1000 instead of 900. |
| E5. Local validation | Passed. Both repair iterations ran `run_local_validation.sh` after the last edit and before committing, exiting 0. Fixture tests are excluded from that helper's pytest run; E4 checks them separately. |
| E6. CI | Live wait passed: the sole `ci_wait.sh` call exited 0 on the final head, with all ten checks passing. Failed-check conversion and its seeded-defect path were not exercised: iteration 2's adversary found MD012 before the first CI wait, and its finding drove the repair. |
| E7. Inline replies | Passed. Both changing iterations recomputed dispositions, successfully called the reply helper for both roots and appended fresh receipts atomically. The no-commit iteration returned no roots. Each thread retained one owned reply and remained unresolved; the ledger recorded the boundary as addressed and the false claim as deferred. |
| E8. Summary | Failed content accuracy. One marked summary was posted before the terminal metric and included both dispositions and the open suggestion. Its iteration-3 line nevertheless said "no findings", although the adversary had returned the suggestion listed below it. |
| E9. Other writes | Passed for executed writes. Snapshot differences were limited to fixture heads, replies, their empty `COMMENTED` reviews and the summary. A PR-body edit was attempted and denied; the body and other metadata stayed unchanged. |
| E10. Dispatch | Batching, selection, sweeps, adversaries and models passed. Response handling failed: the host added a missing final brace to the selected iteration-2 `tests` response before validation, without validating the original or requesting a resend. The other 39 panel/adversary responses matched their validation inputs. |
| E11. Reviewer budget | Failed adherence. Every panel batch included the background timer, but all four timers stopped before the final validation results returned. Expiration and cancellation were not exercised. |
| E12. Environment and isolation | Failed. All 113 environment observations named the repository's Python 3.14.6, and the install checkout was unchanged. However, one `gh pr edit` was denied, and both adversaries read snippets from earlier scenario records through repository-wide searches. |
| E13. Host checkout | Passed. The host ended on the fixture branch at the final head with a clean working tree. |
| E14. Metrics | Passed. Three iteration metrics matched history, followed by one `SUCCESS` terminal metric. |

The receipt and timer failures depart from
[reviewer orchestration](../../docs/reviewer-orchestration.md#completed-reviewer-responses).
The original malformed response fails the validator; the host's repaired copy
passes. A later full sweep supplied valid replacement receipts before the
next edit, so the final panel evidence passes E1, but that does not establish
correct malformed-response handling in the earlier pass. These failures are
tracked in [#43](https://github.com/pulsedemon/pr-review-loop-skill/issues/43)
and [#44](https://github.com/pulsedemon/pr-review-loop-skill/issues/44).
Together with E8, they prevent an unqualified orchestration or posting
correctness claim. The audit covers E1 through E14 and departures observed
while reading their evidence, not exhaustive skill compliance or review quality.

Follow-up, 2026-11-17: bounded Claude Code checks (`claude-opus-5-5`, Claude
Code 2.1.322) replayed iteration 3's recorded state, empty panel result and
merged partitions without a live loop. At `3e4b146` the Step 5 replay wrote
`iteration 3: a full review found nothing blocking.`, omitting the open
suggestion, and its iteration-2 line omitted that iteration's suggestion too.
At `e16e794`, which records the approving iteration's merged findings and
sources each line from history, a Step 5 replay on the recorded state and a run
that started at §4i both wrote that iteration 3 had no blockers and one
suggestion, and named iteration 2's suggestion. The §4i run recorded the
suggestion in `history[2].findings`, and its state validated against the schema.
Each run is one sample. Posting, replies, the terminal metric and an older-state
approval entry before the final iteration were not exercised. Evidence is
retained locally under ignored
`docs/superpowers/reviews/2026-11-17-step5-iteration-lines/`.

| Scenario 26 check | Result |
| --- | --- |
| 1. Reviewer batching | Passed. The initial panel, selected panel and two sweeps each launched in one message. |
| 2. Delta-gate batching | Passed. Iteration 2 launched eight gates together; iteration 3 launched eleven together. |
| 3. Sequential fallback | Not run; this host supports parallel launches. |
| 4. Persona selection | Passed. Iteration 2 carried over `correctness`, `requirements` and `comments`; gates added `tests` and `yagni`, selecting five reviewers. Iteration 3 selected none. Both zero-blocker partial passes triggered eleven-persona sweeps. |
| 5. `cost_saver` routing | Not run; the profile was `balanced`. |

There were 59 child launches: 38 panel reviews, 19 gates and two adversaries.
Each launch joined to its native transcript. Requested aliases resolved to
`claude-sonnet-5-5`, `claude-haiku-5-5` and `claude-opus-5-5`, respectively.
Both adversaries ran on the approval path; no forced shallow-review path ran.
All final sweep and adversary validations passed.

Budget recipe: every panel launch message also started `sleep 1800` in the
background with `timeout: 1860000`. Each timer's `TaskStop` shared a message
with the last validation command for that batch, before its result was known.
No per-batch `date +%s` launch receipt was recorded. This run therefore does
not establish independent adherence to the recipe. No timer expired.

The native session lasted about 910 seconds; the loop's terminal metric
recorded 881. Native counters total 14,279,174 tokens for the parent and
4,744,585 for its children, including 16,871,967 cached-input tokens across
both. Claude Code estimated USD 10.93 at API rates; billed cost was unavailable.
These figures exclude setup, plan review and the permission probe. Raw traces,
before/after snapshots, state, commits, independent fix checks, response
comparisons and per-rule judgments are retained locally under ignored
`docs/superpowers/reviews/2026-11-17-claude-live-edit-run/`.

This run observes live edits, guarded pushes, inline replies, summary transport
and a green final CI check. It does not verify failed-CI conversion, full
orchestration or summary correctness, timeout handling, `cost_saver`, a host
without parallel support, interactive permissions, bot comments, Sonar, or
review quality. The target was this skill's repository, with its instructions
and previous scenario records available to the host. The adversaries' searches
returned prior scenario snippets, so this is not an isolated evaluation. The
fixture PR was closed unmerged afterwards and both disposable remote branches
were deleted. No second full host run was made.

## Reviewer-response handling in Claude Code, 2026-11-17

Bounded host checks for
[issue #43](https://github.com/pulsedemon/pr-review-loop-skill/issues/43) and
[issue #44](https://github.com/pulsedemon/pr-review-loop-skill/issues/44).
Each run gave a fresh headless Claude Code 2.1.322 parent on `claude-opus-5-5`
a read-only `git archive` export of the pin and a local fixture repository with
a one-line diff and no GitHub access. The prompt started the loop at §4b with
`approvers_required` limiting the panel to two personas. Reviewers ran on
`sonnet` under the default routing. Every persona file in the export held the
same generic text: run `review-tool <persona>` and reply with its output
unchanged. The tool's logic and replies were encoded, so a parent reading the
persona files learned nothing about which reviewer misbehaves.

- Run A, `correctness` and `tests`: `tests` first replies with valid JSON
  missing its final `}`, and with a different valid object to any later
  message.
- Run B, `correctness` and `security`: `security` replies only once the
  parent's 30-minute timer has finished, so its reply arrives late.
- Run C, `correctness` and `tests` at iteration 2: a delta-gated pass ran
  `correctness` alone, so §4d's forced full sweep launched a second batch in the
  same session.

A `python3` shim logged every `validate_reviewer_output.py` call's argv, exact
input bytes and exit code. A judge compared those inputs with each child's
`SubagentHandback` message and ordered calls by transcript line and message id.

Run 1 was a baseline at `07ff2de` (`main`). Run 2 was the tested pin
`e37d8e2`, which adds one guidance sentence. The first baseline A, B and C
hosts read the stub reply files before launching reviewers, so those runs were
discarded and repeated with the encoded tool. The first pin A host read the
tool's source and was repeated once.

| Rule | `07ff2de` | `e37d8e2` |
| --- | --- | --- |
| Original malformed bytes validated and rejected (A) | Passed | Passed |
| Receipt only for a validated genuine resend, through `SendMessage` (A and C's sweep) | Passed | Passed |
| Foreground `date +%s` launch receipt per batch (A, B, C) | Failed: A and both C batches folded it into the timer as `date +%s; sleep 1800`, so it returned nothing at launch; B passed | Passed in all four batches |
| Timer stopped only after every validation result returned (A, C) | Passed in A and both C batches | Failed in both C batches: `TaskStop` shared a message with the last validation call; A passed |
| Expiry: timer ran 1800 s, `security` recorded `timed out`, late reply reached the parent and was discarded unvalidated, `REVIEW_INCOMPLETE` with no success summary (B) | Passed | Passed |
| No edits, commits or writes outside the run (all) | Passed | Passed |

The timer-stop failure reproduces the edit-path run's. It happened only after
the parent had loaded the deferred `TaskStop` schema: in 7 of 11 such batches
across this record's runs (discarded ones included) and the edit-path run, and
in neither batch where `TaskStop` was still deferred. With the tool loaded, the parent issues the stop
in parallel with a validation it expects to pass. The guidance makes the stop
wait for "a validated response" but not for the validation's result. One
sample per run at each pin cannot show a fix, and no further fix cycle was run.

This record establishes original-byte validation, resend, timeout recording
and late-output discard in Claude Code with stub reviewers. It does not
establish them with real reviewers, through a host's own delta-gate pass, or
with the adversary. The receipts and launch times come from these runs only.
Traces, validator logs, state, judge output and the harness are retained
locally under ignored
`docs/superpowers/reviews/2026-11-17-claude-reviewer-handling/`.

## Validation status

**Status:** `design_only`
**Evidence:** The dated multi-iteration Codex run and Claude Code edit-path run above establish checks 1, 2, and 4 at their pinned revisions; the Claude dry run establishes checks 1 and 4 at its pin. The edit-path record separately reports its receipt, budget, summary and isolation failures; its follow-up Step 5 replay shows the summary failure fixed at `e16e794`. The reviewer-response record establishes original-byte validation, resend, per-batch launch receipts and budget expiration with late-output discard at `e37d8e2`, with stub reviewers.
**Missing evidence:** Dated host runs covering conditional fallback (check 3), `cost_saver` model routing (check 5), and a Claude Code timer stop that waits for the last validation result in every batch (the reviewer-response record failed it). The Claude live edit-path run also leaves failed-CI conversion unverified.
