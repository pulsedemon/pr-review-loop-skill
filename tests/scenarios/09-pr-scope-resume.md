# Scenario 09: PR-scope check, resume after recorded decision

**Pressure type:** resume discipline / no re-prompt

## Setup

A prior run of the loop has already passed Step 3.5 and recorded a decision. The user re-invokes the loop on the same PR (e.g. CI failed mid-Step 4 and they want to continue). On resume, the orchestrator reaches Step 3.5.

Three sub-scenarios cover three of the four resumable `user_decision` values (`agent_failed` resumes like `declined_agent`, pinned in `scripts/tests/test_pr_scope_step.py`); a fourth covers the crash-mid-step recovery; a fifth covers the terminal `abort` re-entry.

### 9a. `user_decision: "not_prompted"` (under threshold last time)

`.git/pr-loop/pr-scope.json` exists with:

```json
{
  "threshold": 1000,
  "new_loc_total": 282,
  "verdict": "under_threshold",
  "user_decision": "not_prompted"
}
```

### 9b. `user_decision: "declined_agent"` (over threshold, user said no)

`.git/pr-loop/pr-scope.json` exists with:

```json
{
  "threshold": 1000,
  "new_loc_total": 1248,
  "verdict": null,
  "user_decision": "declined_agent"
}
```

### 9c. `user_decision: "continue"` (agent returned splits, user continued anyway)

`.git/pr-loop/pr-scope.json` exists with `verdict: "request_split"`, a populated `splits` array, and `user_decision: "continue"`.

### 9d. crash mid-Step 3.5 (file exists, no decision)

`.git/pr-loop/pr-scope.json` exists with `new_loc_total`, `per_file`, and `excluded_paths` from a prior `scripts/pr_scope_step.py plan` + `persist` (substep 2) but `user_decision` is missing or empty: the prior run crashed before substeps 3–4 (user prompt / gate verdict) ran.

### 9e. `user_decision: "abort"` (terminal status from prior run)

`.git/pr-loop/pr-scope.json` exists with `verdict: "request_split"` and `user_decision: "abort"`. The prior run already terminated with `SCOPE_SPLIT_RECOMMENDED` and posted the Step 5 comment.

### 9f. state-first persist crash (decision in state, sidecar missing)

`state.json` carries `pr_scope.user_decision` in `not_prompted`, `declined_agent`, `agent_failed`, or `continue` from a state-first `persist`, but `.git/pr-loop/pr-scope.json` is absent. Resume must honor the recorded decision without re-prompting (see `test_plan_pr_scope_step_resume_honors_state_decision_without_pr_scope_file`).

### 9g. persisted partial count (sidecar optional, no decision)

`state.json` carries `pr_scope` with `new_loc_total` / `per_file` from substep 2 `persist` before the run crashed; `pr-scope.json` may be missing and `user_decision` is empty. Resume must call `plan` with the persisted `pr_scope` JSON and the sidecar-existence probe, reusing counts without re-running `count_new_loc.sh` (see `test_plan_pr_scope_step_resume_reuses_state_counts_without_pr_scope_file`).

## Baseline behavior (no skill)

_Filled in after a RED run. Capture verbatim, e.g.:_

- On resume, the loop re-prompts for scope, re-spawning the agent and incurring duplicate cost / user friction.
- Or the loop silently continues even after the user aborted, contradicting the prior terminal decision.

## With skill (target behavior)

- **9a, 9b, 9c, 9f:** Step 3.5 is skipped silently. The recorded `user_decision` is honored even when `pr-scope.json` is missing. Loop proceeds to Step 4. **No user prompt fires.**
- **9d, 9g:** Step 3.5 is re-run starting from substep 2 (`plan` on a persisted `pr_scope` count record, then `persist`). The existing `new_loc_total`, `per_file`, and `excluded_paths` are reused; `count_new_loc.sh` is NOT re-invoked. If the reused count is under threshold, continue silently with `user_decision: "not_prompted"` (zero prompts). If over threshold, the user receives exactly one scope prompt.
- **9e:** The orchestrator does NOT continue to Step 4. It re-emits terminal status `SCOPE_SPLIT_RECOMMENDED` and jumps to Step 5, which idempotently updates (not appends to) the existing marker-tagged summary comment on the PR.

## Pass/fail criteria

- **Pass:** Each sub-scenario's documented behavior is exhibited. Specifically:
  - 9a/9b/9c/9f: zero user prompts; loop enters Step 4 within one iteration of resume.
  - 9d/9g: `count_new_loc.sh` is not re-invoked; under-threshold reuse yields zero prompts and `not_prompted`, over-threshold reuse yields exactly one scope prompt.
  - 9e: loop terminates with `SCOPE_SPLIT_RECOMMENDED`; PR comment is updated in place, not appended.
- **Fail:** Any of:
  - The agent is re-spawned in 9a/9b/9c/9f.
  - The loop continues to Step 4 in 9e.
  - The user is prompted in 9a/9b/9c/9f.
  - A duplicate summary comment is posted in 9e.

## Validation status

**Status:** `ci_trusted`
**Evidence:** Deterministic Step 3.5 coverage in `scripts/tests/test_pr_scope_step.py` proves resume honors recorded decisions, reuses partial count state, and re-emits the abort terminal status without re-prompting. `tests/bats/test_step5_summary_contract.bats` separately guards the Step 5 single-comment split routing prose/template contract, but it is not an end-to-end comment-posting test.
