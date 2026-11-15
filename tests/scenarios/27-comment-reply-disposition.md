# Scenario 27: Inline-comment disposition + reply + SUCCESS gate

**Type:** manual host regression check of changed discussions, §4i dispositions, and the completion gate.

## Setup

use an authorized pr or a local fixture with real commits and a local bare
remote. stub GitHub calls for the local fixture and retain their complete trace.
start with an unresolved external root and one owned marker reply citing a
verified fix. include bot feedback and model feedback posted through a human
account. keep source, state, and remote snapshots for each case.

run the actual fetch, reply, decision, and state helpers from the host. injected
review receipts may isolate the discussion lifecycle, but validate them and
identify them as injected. they do not establish reviewer dispatch or quality.
the lifecycle contract lives in
[`docs/comment-handling.md`](../../docs/comment-handling.md).

## Checks

1. complete two fresh runs on the same fixed head. each starts with empty local
   history and ledger, verifies the earlier fix, reuses its exact reply body and
   SHA, and records an addressed disposition. the second run makes no reply write.
2. add a late bot objection under that handled root. the host reconsiders the
   whole thread and follows the full-panel decision within the remaining budget.
   edited root, reply, issue, and review bodies, changed review state, and an
   externally reopened thread receive the same treatment.
3. unchanged content, response ordering, fetch timestamps, line movement,
   resolution alone, and loop-marker activity do not restart review. a
   reply-created verified review artifact on the final iteration does not
   restart review, while changed feedback at the iteration cap returns
   `MAX_ITERATIONS`.
4. reproduce a supported objection, fix it, verify it, commit, and push before
   updating the owned reply. record the exact PATCH endpoint, reply id, full body,
   and pushed SHA. one marker reply remains.
5. exercise POST for a root with no marker, PATCH for a changed owned body, and
   no mutation for an identical body. foreign or duplicate markers stop writes.
6. defer a root in iteration 1, then make a responsive code change in iteration 2
   with unchanged discussion text. §4i selects that ledgered root, rejects an
   omitted fresh receipt, and updates its reply and ledger to addressed. a code
   change that leaves the old disposition valid reuses its exact body without PATCH.
7. a failed verification does not replace a supported reply with an invented
   deferral. failed fetch, scan, or reply operations return `REVIEW_INCOMPLETE`
   without advancing the ledger or reviewed snapshot or posting a final comment.
8. interrupt after a successful POST reply and its associated empty
   `COMMENTED` review but before history append. the old snapshot remains;
   resume stays on the same pending iteration, replay reuses the exact reply
   without another POST or review, and then records the successful disposition.
   an unrecorded push still follows the existing resume refusal.
9. the ledger, original pre-reply reviewed snapshot, and reply receipt advance
   in one successful append. the final fetch must not replace that snapshot. an
   older required root with no successful disposition prevents completion even
   after external resolution.
10. retain resolved-thread roots and external replies across pagination, including
    bot follow-ups. the 247-thread volume fixture preserves distinct large bodies
    through fetch, comparison, and persistence. incomplete REST/GraphQL joins fail.
11. surface every unresolved or unanswered thread. neither reply handling nor
    completion resolves or reopens a thread automatically. dry runs make no writes.

## Pass criterion

all checks pass with their evidence source identified. record the observed host
decisions, exact tool traces, elapsed time, and available cost.
state the limits of injected receipts and any checks established only by
deterministic integration tests. prose-only answers do not establish host behavior.

## observed host run, 2026-09-18

the Codex host exercised the changed lifecycle from base `4f4f9b7` against real
local commits and bare remotes. GitHub calls used a local adapter that refused
unsupported endpoints. panel and adversary receipts were injected and passed
schema and identity validation. CI was skipped; this run establishes disposition
and persistence behavior, not reviewer dispatch, finding quality, live GitHub,
or the final summary workflow.

| case | observed result |
| --- | --- |
| two fresh runs at `55c6ba52a3505eb2fdb3bbfbf8dd469736fdd8db` | inspected the cited trim fix and executed current behavior in each run; reused the exact body and SHA; zero POST/PATCH calls; each fresh state recorded addressed and passed completion |
| new bot objection about `None` | reproduced `AttributeError`, verified the fix, committed and locally pushed `6f1a9e79fd0a14dd715e2629cf2e6281afc34a20`, then patched reply 55 once and completed after a review of the new head |
| unchanged discussion after code changes | recorded a factual deferral in iteration 1; fixed, verified, and pushed `cb31d3b68b1047b995026c0e30148e9480d108e6` in iteration 2; §4i selected root 10; omitted receipt exited 2 with byte-identical state; one PATCH changed the disposition to addressed |
| later annotation at `ac586925d9a4d31b0514aaf6e172a6219c11cc64` | verified the earlier fix still applied; reused the exact addressed body and original fix SHA; no additional PATCH; fresh receipt and subsequent review completed |
| injected PATCH failure | helper exited 1 and host reported `REVIEW_INCOMPLETE`; state remained byte-identical |
| failed behavior verification | verification command exited 1; host reported `REVIEW_INCOMPLETE`, retained the supported reply, and made no reply or history writes; remote and state remained byte-identical |
| dry-run | valid record-only append retained the original snapshot and empty ledger, then reported `DRY_RUN_COMPLETE`; no reply helper or remote writes ran |
| reply-only interruption | successful PATCH followed by a shell boundary before append left state unchanged; production resume accepted matching recorded heads; replay performed no mutation, then atomically appended and completed |
| unrecorded push | production resume returned `EXTERNAL_PUSH`; the host did not replay across the mismatched head |

all writes targeted `PATCH repos/owner/repo/pulls/comments/55` for root 10.
the three fixtures each retained exactly one owned marker. no resolution or
reopening API was called. original fetched snapshots were compared with their
persisted history values; final fetches remained separate. fixture worktrees
were clean after the runs.

the main host interval was 519 seconds. failed-verification and dry-run cases
took a separate measured 66 seconds. model tokens and cost were unavailable.
the local trace and full submitted bodies are retained in
`/private/tmp/pr146-host.KeCMDa/host-notes.md` and
`/private/tmp/pr146-host.KeCMDa/all-mutations.json`; those temporary paths are
local evidence, not repository dependencies.

separate hermetic CLI execution before regression edits covered POST/PATCH/no-op,
all edited feedback sources, reopening, unchanged second runs, failure/replay, and
original-snapshot persistence in 17.383 seconds. the corrected 247-thread fetch
preserved all 247 external replies and distinct large bodies in 13.54 seconds;
the complete envelope then passed stdin comparison and persistence checks.
these deterministic boundaries are retained in
`tests/bats/test_fetch_pr_comments.bats`, `tests/bats/test_reply_pr_comments.bats`,
`scripts/tests/test_discussion_changes.py`, `scripts/tests/test_loop_boundaries.py`,
and `scripts/tests/test_pr_loop_state.py`. dry-run routing retains its existing
guard in `tests/bats/test_step5_summary_contract.bats`.

_validated with the Codex host on 2026-09-18: PASS._

## observed host run, 2026-09-21

the local host exercised the issue #150 reply-review lifecycle with stubbed
GitHub calls. the baseline core suite completed in 3.038 seconds. the fixed
all suite completed in 8.155 seconds at real local commit and matching head
`6ca1ad1e13e023e1ad3c6354527adfdddbd27930`; required review receipts were
injected and CI was skipped. the fixed suite exercised POST, fetch, resume,
append, and completion at iterations 1 and 15.

the reply fixture created reply `999` under root `10`, associated with empty
`COMMENTED` review `888`; root `10` belongs to review `77`. interruption left
state byte-identical, resume selected the same pending iteration, and replay
reused the exact reply without an extra POST or review. a missing-receipt
append exited 2 with unchanged state. the successful append retained the
original pre-reply snapshot and receipt atomically. the host routed artifact-only
completion to `SUCCESS` at iterations 1 and 15. the host also observed
`DRY_RUN_COMPLETE` with the original snapshot preserved and no POST or PATCH.

the additional host observation took 10.159 seconds with matching local and
bare-remote heads. inline bot and human-model objections, empty approvals and
change requests, and a substantive review body each requested the full panel at
iteration 1 and returned `MAX_ITERATIONS` at iteration 15. tokens and cost were
unavailable.
the actual dry-run was record-only, preserved the original snapshot, and made
no ledger, POST, or PATCH change.

this evidence covers the stubbed local lifecycle and injected receipt path. it
does not establish live GitHub behavior, reviewer dispatch, CI, or summary
publication.

_validated with the Codex host on 2026-09-21: PASS._

## Live GitHub approval path, 2026-11-14

The Codex parent ran the normal loop on
[PR #5](https://github.com/pulsedemon/pr-review-loop-skill/pull/5) at
`678b59821511b16f3962bae0f9376adbeaae4631`, using that revision's skill with
startup sync disabled. Fresh state retained the new `0/false/false` promotion
settings and required the full panel. The panel ran as one batch on
`gpt-6.1-sol`; a fresh `gpt-6-astra` adversary received all raw responses,
including one docstring nit. Every response passed schema/identity validation,
with no shallow flags or blockers. The adversary approved without findings.

The real CI helper observed ten passing GitHub checks. Fresh REST/GraphQL
fetches contained no external comments or review threads, and fresh local and
remote heads both matched the reviewed revision. The actual append and
completion helpers permitted success in iteration 1. The
[summary comment](https://github.com/pulsedemon/pr-review-loop-skill/pull/5#issuecomment-6883576114)
was posted before the terminal helper recorded `success` at
`2026-11-14T20:15:06Z`.

This establishes actual dispatch, live GitHub/CI, and the no-edit approval
path. The subsequent docstring cleanup and this record change no helper or
executable test behavior. The run does not establish inline reply handling,
the edit path, delta-gate dispatch, dirty-tree reviewer conduct, or another
parent host. Injected edit/failure decisions remain documented in
[Scenario 24](24-adversary-full-default.md#changed-default-fixture-run-2026-11-14).
Raw receipts, state, CI output, and discussion/head snapshots were retained
locally under ignored `docs/superpowers/reviews/2026-11-14-review-quality/pr-loop/`.

## Local multi-iteration completion

The [2026-11-15 Codex run](26-parallel-reviewer-fanout.md#live-multi-iteration-codex-run-2026-11-15)
records completion after a real fix and local push, with captured summary
transport and empty discussions. It adds no inline-reply or live GitHub evidence
and does not establish any additional complete check in this scenario.

## Validation status

**Status:** `manual_validated`
**Evidence:** the dated 2026-09-18 host run above records prior-fix inspection, two fresh runs, real committed and pushed fixes, owned reply updates, atomic snapshots, and interruption recovery. the dated 2026-09-21 host run above records the issue #150 reply-review lifecycle, artifact association, resume/replay, and original-snapshot checks. the cited regressions cover deterministic comparison, transport, ownership, and budget boundaries; injected review receipts do not establish reviewer quality.
