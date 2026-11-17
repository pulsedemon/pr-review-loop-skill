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

## Validation status

**Status:** `design_only`
**Evidence:** The dated multi-iteration Codex run above establishes checks 1, 2, and 4 at its pinned revision, and the dated Claude Code dry run establishes checks 1 and 4 for that host at its pin; earlier partial observations remain recorded above.
**Missing evidence:** Dated host runs covering conditional fallback (check 3), `cost_saver` model routing (check 5), independent adherence to the reviewer-budget recipe, and reviewer-budget expiration and cancellation.
