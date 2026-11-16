# scenario 24: full adversary context and required review completion

**Type:** manual host check of the default panel visibility and approval-path routing.

## setup

use a local fixture pr with code changes, a fixed head, and the effective panel's
actual validated responses. start at §4d.0 with zero blockers. retain a tool trace
and before/after git status and head observations. stub GitHub calls locally so
the scenario cannot post to a live pr.

run three independent cases from a fresh copy of the same pre-final state:

- invalid adversary response: inject schema-invalid output.
- shallow adversary response: inject `verdict: approve`, empty findings, and no
  `evidence.files_read`.
- valid final response: inject `verdict: approve`, empty findings, and nonempty
  `evidence.files_read` on the last permitted iteration.

do not supply `adversary_panel_visibility`. include the full panel JSON in the
adversary invocation, as selected by the default. record the exact injected
responses and their validation results. the injection tests host routing, not
the adversary's ability to discover findings.

also record an actual fresh adversary dispatch and its returned response to
establish delivery of the full panel input.

## checks

1. default visibility is `full` in state and the adversary receives the full
   panel responses, including findings.
2. invalid output records `adversary_error` with no replacement adversary
   response. shallow output records the actual response and shallow flag.
3. both incomplete cases record equal before/after head SHAs, actual findings,
   completed panel receipts, and skipped CI, then exit `REVIEW_INCOMPLETE`.
   neither enters the edit phase, commits, pushes, replies, or posts a final
   success comment. no synthetic blocker or new legacy approval counter is written.
4. the valid case passes the actual completion helper on the last permitted
   iteration after CI and the final comment fetch. local and remote head
   observations are fresh. the host reaches `SUCCESS` without another iteration.
5. iteration and terminal metrics reflect the persisted outcome. record elapsed
   time and any available model cost; mark unavailable cost as unavailable.

## pass criterion

all checks are observed in a host tool trace. helper unit tests and prose-only
answers cannot establish host routing. completion mechanics remain canonical in
[`docs/exit-conditions.md`](../../docs/exit-conditions.md#required-reviews-at-completion).

## observed host run, 2026-09-18

the Codex host ran this change on base `0b5fd54` against a local normalization
fixture at head `3f47d7f9e81c98378beeef814b5459ecb8b78e1d`. each case started at
iteration 14 with `max_iterations: 15` and required reviewers `tests,security`.
both panel responses passed schema and dispatched-identity validation.

| response | validation | observed outcome |
| --- | --- | --- |
| approve with empty findings and an extra `unexpected` property | exit 1 | error persisted, `REVIEW_INCOMPLETE` |
| approve with empty findings and no evidence | exit 0, shallow flag `adversary` | actual response persisted, `REVIEW_INCOMPLETE` |
| approve with empty findings and nonempty read evidence | exit 0, no shallow flag | `SUCCESS` at iteration 15 |

the host invoked the real history and metric helpers. both incomplete cases
skipped CI, produced no GitHub calls, and left the head and worktree unchanged.
the existing legacy approval counter stayed at zero. no synthetic blocker,
edit, commit, push, reply, or final comment was produced.

a separate fresh adversary received all five inputs with the full raw panel
responses, including their findings, evidence, and distinct notes. it read the
fixture and returned a valid approval confirming that input. the host then ran
the actual CI wait, comment fetch including GraphQL threads, fresh local and
stubbed remote head observations, and completion helper. completion returned
`terminal_status: null, continue_full_panel: false`; state and terminal metrics
recorded `SUCCESS` at iteration 15. only the fixture received a summary comment.

the injected cases took 194.836 seconds; the actual-dispatch follow-up took
160.113 seconds. model tokens and cost were unavailable. panel findings were
empty, so this run establishes routing and full-object delivery, not retention
of nonempty findings or adversary finding quality.

_Validated with the Codex host on 2026-09-18: PASS._

## Changed-default fixture run, 2026-11-14

A fresh Codex parent exercised the helpers at
`90e55936e7b8584562c6856033e47cbf7361073a` with injected reviewer, adversary,
gate, metadata, comment, and CI receipts. All executed helper and schema files
were byte-checked against that pin after the parent checkout advanced. Fixtures
used real commits and owned local bare remotes; Git allowed only file transport.
The GitHub adapter recorded calls and rejected unsupported requests.

| Case | Observed host behavior |
| --- | --- |
| Fresh defaults | `state_init.sh` stored `0/false/false`; matching, endorsed, and solo anchored suggestions stayed nonblocking; no edit or remote change |
| Explicit adversary blocker matched to a nit | Promotion retained the blocker's own diagnostics and combined provenance; the host reproduced the schema defect, repaired it, verified the command, committed, and pushed locally |
| Invalid required panel response | Validation rejected the verdict; history retained the error and completion returned `REVIEW_INCOMPLETE`, with unchanged tracked bytes and no review push or summary write |
| Iteration-2 delta selection | Four validated gate receipts plus blocker carryover selected `correctness/tests`; zero blockers forced a five-persona sweep before completion, still in iteration 2 |

The fixture repair moved from
`1e6ce836f5fbd82d9eaabe8851ef939853067bcf` to
`10370f9f27a8998519f0e6a4d086d3747ecee049`. The full sweep retained one
nonblocking nit in its promotion output, replaced the partial review receipts,
and passed the actual completion helper at that unchanged repaired head.
This bounded fixture did not post a summary or record terminal success.

The run took 703.2 seconds; tokens and cost were unavailable. Raw commands,
receipts, source hashes, state, remote snapshots, and the host's decisions were
retained locally under ignored
`docs/superpowers/reviews/2026-11-14-review-quality/host-check/`.

These cases establish the fresh host's decisions and real helper/Git behavior.
They do not establish actual reviewer dispatch, parallel gates, model quality,
live GitHub/CI, another parent host, or all checks in this scenario. In
particular, the invalid response here came from a required panel persona;
the dated adversary-specific cases above remain historical evidence.

For actual panel/adversary dispatch and GitHub completion, see the
[live approval-path record](27-comment-reply-disposition.md#live-github-approval-path-2026-11-14).

## Changed-default fixture run in Claude Code, 2026-11-16

A fresh Claude Code 2.1.322 parent ran the four cases against a read-only
`git archive` export of `656ced745baa07eaa1434a1f091a3c1dcd8f49ef`. Witch launched
it headless on `claude-opus-5-5` at high effort, in the `auto` permission mode
with no prompt handler. Its subagent, web and MCP tools were disabled, so it
wrote every reviewer, adversary and gate receipt itself. The export omitted
`tests/scenarios`, which records the earlier outcomes, and stayed byte-identical
to the pin. Fixtures used real commits and owned local bare remotes; Git allowed
only file transport. A `gh` adapter served read calls and refused the one write
it was probed with.

| Case | Observed host behavior |
| --- | --- |
| Fresh defaults | `state_init.sh` stored `0/false/false`; two matching panel suggestions, an endorsed suggestion, and a solo anchored adversary suggestion stayed nonblocking; the host made no edit, and tracked bytes, head and remote did not change |
| Explicit adversary blocker matched to a nit | Promotion kept the blocker's own detail and fix with `tests` and `adversary` provenance and no promotion record; the host reproduced the seeded boundary defect, changed one line, passed local validation, committed, and pushed locally through `safe_push.sh` |
| Invalid required panel response | Validation rejected the `security` response; history kept the error and the other reviewers' receipts, and no finding came from the invalid output; the host recorded `REVIEW_INCOMPLETE` with no adversary, edit, push or summary write, and tracked bytes, head and remote did not change |
| Iteration-2 delta selection | Eight validated gate receipts, two rejected ones that failed open, and blocker carryover selected `correctness`, `tests`, `readability`, `comments` and `error_handling`; zero blockers forced the full default panel at the same head, still in iteration 2 |

The pricing repair moved from `0c73f0e6f7fe4807d3bc122f330475acb128bb22` to
`f0b3a2e0474ddbb6a5ec90cdd1dbe8cc360fbbae`. The delta fixture's own iteration-1
repair moved from `e94fae2d6d02e5d92f6cd221f89c7e3ec519c363` to
`6f7fcf0aaa8d09eb7d6a1946b5bbd5354a07d872`. Its sweep kept one suggestion open,
deferred one out-of-scope finding, and replaced the partial review receipts. The
first and fourth cases passed the actual completion helper at unchanged heads.
No case posted a summary or recorded terminal success.

The host's `python3` was 3.11.4, below the 3.12 minimum in `SKILL.md`, and no
helper refused it ([issue #15](https://github.com/pulsedemon/pr-review-loop-skill/issues/15)).
The launching session replayed the 132 logged Python helper steps it could
rerun deterministically from the pin under Python 3.14.6. Every exit code and
output matched, and each `append-history` result matched its retained state.
Shell helpers and the PR-scope step ran only under 3.11.4.

The trace shows no subagent launch, no permission denial, and no read of the
installed skill, the source checkout, or earlier evidence. The host's ambient
configuration loaded one unrelated skill, `commit-message`.

The session lasted 845 seconds; the host timed its own work at 813. Its native
`claude-opus-5-5` counters total 13,523,094 tokens, including 13,190,568 cached
input tokens. Claude Code estimated USD 6.25 at API rates; billed cost was
unavailable. The
native trace, launch settings, commands, receipts, state, Git snapshots, and
replay results are retained locally under ignored
`docs/superpowers/reviews/2026-11-16-claude-host-check/`.

These cases establish a Claude Code parent's decisions and real helper and Git
behavior on this pin, in a headless session. They do not establish actual
reviewer or gate dispatch, parallel batching, the reviewer budget, model
routing, review quality, live GitHub or CI, inline replies, summary posting,
permission prompts in an interactive session, or all checks in this scenario.

## Actual multi-iteration dispatch

The [2026-11-15 Codex run](26-parallel-reviewer-fanout.md#live-multi-iteration-codex-run-2026-11-15)
records actual panel and adversary dispatch, a pushed repair, and an injected
required-panel validation failure. It does not rerun this scenario's
adversary-specific invalid/shallow cases or last-iteration approval check.

## Validation status

**Status:** `manual_validated`
**Evidence:** the dated host run above records validation, terminal decisions, state and metrics, unchanged checkout, and GitHub call observations for the injected and actual-dispatch cases.
