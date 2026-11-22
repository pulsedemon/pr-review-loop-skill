# Reviewer orchestration mechanics (SKILL.md §4b)

This document owns the orchestrator-side rules for handling reviewer subagent JSON, materializing it (or not) on disk, recording the procedure-expectation contract that drives shallow-review detection, and the reviewer budget. `SKILL.md` §4b keeps the strict-JSON / `output.schema.json` reference, the `evidence` vs `finding_evidence` one-liner, the scope-discipline hard rule, and the Move C summary.

## Reviewer output handling

Reviewer JSON is transient; synthesized partitions, `reviewers_completed`, and `reviewer_errors[]` persist to state. Per-file materialization is optional: [`scripts/validate_reviewer_output.py`](../scripts/validate_reviewer_output.py) and [`scripts/promote_findings.py`](../scripts/promote_findings.py) accept stdin, and [`scripts/flag_shallow_reviews.py`](../scripts/flag_shallow_reviews.py) accepts a `jq -s` concatenated array, so piping in-memory outputs is sufficient.

If you DO persist per-reviewer files, emit each one in a single `Write` (or `Bash` heredoc) with full content; **never pre-create an empty file** (`: > path`, `touch`) and then `Write` over it, because `Write` refuses to overwrite a path it has not `Read`, and every parallel write will fail at once.

## Completed reviewer responses

Start each iteration with empty `reviewers_completed` and `reviewer_errors`.
Validate each actual response with `validate_reviewer_output.py --reviewer`
using the dispatched persona name. Add that name only after validation succeeds.
Record missing, timed-out, malformed, and wrong-persona responses as errors;
never manufacture an empty review. Preserve valid findings from other reviewers.

A forced full sweep replaces the partial pass's receipts and errors with the
full sweep's results. Selection is not a receipt. Persist the receipts in the
iteration history, including dry runs and incomplete reviews. An unrecovered
required-panel error records an incomplete iteration and exits `REVIEW_INCOMPLETE`.
Receipts establish valid responses, not assigned-file read coverage.

## Reviewer budget

The panel has 30 minutes from its batch launch. Record the launch time (`date +%s`) for each batch as its own foreground call, right after the launch message; folded into the background timer's command, it returns nothing until the timer ends. When the budget runs out, stop waiting. A valid response already received counts. Every reviewer with neither a validated response nor a recorded error is stopped where the host allows and recorded in `reviewer_errors` as `{"reviewer": "<persona>", "error": "timed out"}`. A resend requested for malformed output stays inside the same budget. Anything an overrun reviewer sends later is discarded, not validated, and earns no receipt. Neither a relaunch nor a message to a stopped reviewer recovers a timeout. From there a timeout is handled like any other reviewer error under [completed reviewer responses](#completed-reviewer-responses).

How each host keeps the budget:

- Claude Code: launch reviewers in the background, the `Agent` default, and never pass `run_in_background: false`. In the launch message, also start `sleep 1800` as a background Bash command with `timeout: 1860000`. If that timer finishes on its own first, `TaskStop` each reviewer with neither a validated response nor a recorded error. Once every reviewer has a validated response or a recorded error, `TaskStop` the timer so its exit cannot read as a timeout later. A response is validated only once its validation call's result is back, so `TaskStop` the timer in a later message than the last `validate_reviewer_output.py` call.
- Codex: after the last `spawn_agent`, call `wait_agent` in waits of at most 60000 ms until every reviewer has reported or the budget is spent, then `interrupt_agent` each one still running. `wait_agent` returns on any agent's update, so track which reviewers have reported. An interrupted agent stays alive, so discard what it sends.
- Cursor: launch each reviewer with `run_in_background: true`, and `Await` each with `block_until_ms` set to the time left. Cursor has no call that cancels a subagent, so an overrun reviewer is abandoned, not stopped, and the working-tree addendum still binds it.
- opencode: `task` blocks until the subagent returns and has no timeout or cancel, so the stop cannot be enforced there. The `tests` persona's [mutation-probe bound](../reviewers/tests.md#mutation-probes) is the only limit.
- Witch: launch a batch's familiars in one message; routing is in [`model-overrides.md`](model-overrides.md#witch). The budget applies per familiar, so every panel familiar still running at the budget is stopped and records its own timeout, even when another familiar for that persona validated. Claude parent: launch each familiar as a background Bash command with `timeout: 1860000`, so the host's default limit cannot end it inside the budget, then keep the Claude Code timer and `TaskStop` rules above with each familiar's Bash task in place of a reviewer; `TaskStop` ends the familiar and the commands it started. Codex parent: launch each familiar with `exec_command` using `sandbox_permissions: "require_escalated"` and `tty: true`, poll every session with an empty `write_stdin` until each familiar has exited or the budget is spent, then send `\u0003` with `write_stdin` to each one still running; that stops the familiar, but a command a Codex familiar started can outlive it. A stopped familiar's report is discarded like other late output.

## Procedure expectation

Each persona's prompt requires it to read changed files in full, grep for callers and tests of changed exported symbols, and grep for consumers of new files, *before* forming a judgment. The reviewer SHOULD record what it read in an optional top-level `evidence` object (`files_read`, `symbols_traced`, `notes`) on its output. `evidence` is optional in the schema for backward compat, but the synthesis step in `SKILL.md` §4c flags any reviewer that returns `verdict: approve` with missing or empty `evidence.files_read` as a `shallow_review` for that iteration. Detection is implemented by [`scripts/flag_shallow_reviews.py`](../scripts/flag_shallow_reviews.py); see `SKILL.md` §4c for what the flag triggers.

## Why this prose is load-bearing

The "never pre-create an empty file" rule prevents a real concurrent-write failure mode: when multiple reviewer subagents run in parallel and each tries to overwrite a pre-created empty file, every parallel `Write` call refuses (because none have `Read` it) and the iteration loses every reviewer's output at once. This rule is the reason reviewers have stricken empty-file pre-creation in past PRs.

The shared working tree is the same class of hazard, one layer down. Reviewers run in parallel with each other and with the orchestrator's §4e edit phase, in one checkout, so a reviewer that writes to the tree or "cleans" it can destroy an edit in progress. That happened: a reviewer read a dirty tree as stale drift and reverted it with `git checkout --`, twice, losing the §4e edit silently. The rules reviewers get are canonical in [`reviewers/_working_tree_addendum.md`](../reviewers/_working_tree_addendum.md), linked from every persona and the adversary; `tests/bats/test_addendum_link_sync.bats` pins that delivery.

## See also

- Reviewer output schema: [`reviewers/output.schema.json`](../reviewers/output.schema.json): canonical for required-vs-optional finding fields, including the `scope == "in_scope"` rule that requires `file`/`line`/`detail`.
- Synthesis: [`docs/synthesis.md`](synthesis.md).
- Shallow-review consequences: `SKILL.md` §4c and §4d.0.
