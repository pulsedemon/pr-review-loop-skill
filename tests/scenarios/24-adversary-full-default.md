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

## Validation status

**Status:** `manual_validated`
**Evidence:** the dated host run above records validation, terminal decisions, state and metrics, unchanged checkout, and GitHub call observations for the injected and actual-dispatch cases.
