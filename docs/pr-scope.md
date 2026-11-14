# PR-scope check (SKILL.md §3.5) — Mechanics

This document owns the four-substep mechanics, the verdict-branch table, the non-interactive defaults, and the resume contract for `SKILL.md` §3.5. `SKILL.md` keeps only the user-visible automation contract (when prompts are allowed; the abort path → `SCOPE_SPLIT_RECOMMENDED`); everything below moved here from the original SKILL.

## When this step runs

Skip entirely if `pr_scope=false`. Otherwise:

- On a **fresh** start, run substeps 1–4 below.
- On **resume**, skip substeps when `pr_scope.user_decision` in state is `not_prompted`, `declined_agent`, or `continue` (honor it and proceed to Step 4 even if `<git-dir>/pr-loop/pr-scope.json` is missing after a state-first persist crash). If `user_decision` is missing or empty, re-run substep 2: `plan` with `--existing-pr-scope-json` from the persisted `pr_scope` record (state first, sidecar fallback), `--pr-scope-file-exists` from the sidecar probe, and reuse those counts (not `count_new_loc.sh`). If `user_decision` is `abort`, re-emit `SCOPE_SPLIT_RECOMMENDED` → Step 5.

## "Non-interactive" definition

"Non-interactive" means: stdin is not a TTY, **or** the orchestrator was launched with a non-interactive flag, **or** no user response is received within the orchestrator's prompt timeout. In any of those cases, take the documented default for the prompt without waiting.

## Substeps

1. **Count new LOC.** Run `bash "$SKILL_ROOT/scripts/count_new_loc.sh" <base_branch>`, capturing stdout (line 1 = `new_loc_total`; lines 2+ = TSV `<added>\t<deleted>\t<path>`) and stderr (`# excluded: <path>` or `# excluded (binary): <path>` per excluded file). Pass `excluded_paths` through to the gate agent in step 3.

2. **Compare to threshold.** Run `python3 "$SKILL_ROOT/scripts/pr_scope_step.py" plan` (fresh: `--count-stdout-file`/`--count-stderr-file`; resume: `--existing-pr-scope-json` from state `pr_scope`, `--pr-scope-file-exists` when sidecar exists), then `persist` so `state.json` and `<git-dir>/pr-loop/pr-scope.json` stay in sync (state first, then pr-scope):
   - `action: "continue"` with `verdict: "under_threshold"` and `user_decision: "not_prompted"` → Step 4 silently (**no prompt**), including resume after crash when `user_decision` is still missing.
   - `action: "prompt"` → step 3 (over threshold, or `pr_scope=true`).

3. **Prompt the user.** Ask once: "This PR has \<N\> new LOC (threshold \<T\>). Run the PR-scope agent to suggest how it could be split into smaller PRs?"
   - **No** → `finalize` with `user_decision: "declined_agent"`, then `persist` (infers `action: "continue"` from finalize output); continue to Step 4.
   - **Yes** → spawn one subagent with the prompt from `gates/pr-scope.md`, passing PR metadata + body + linked tickets, the full diff against base, the per-file breakdown from step 1, `new_loc_total`, `max_new_loc`, and `excluded_paths`. The agent returns strict JSON matching `gates/pr-scope.md`; validate any `request_split` payload with [`scripts/validate_pr_scope_output.py`](../scripts/validate_pr_scope_output.py), then `finalize` + `persist` with the gate result.
   - **Non-interactive default:** skip and continue (record `user_decision: "declined_agent"`, proceed to Step 4).

4. **Act on the agent's verdict.** The agent's `verdict` enum is exactly `{under_threshold, atomic, request_split}` (per `templates/state.schema.json` `pr_scope.verdict.enum`); `declined_agent` is a `pr_scope.user_decision` value recorded when the user opts out at substep 3 and is **not** a verdict. The branches:

   | Branch | Action | `user_decision` | Next step |
   | --- | --- | --- | --- |
   | `verdict: under_threshold` | (substep 2 sets this; agent never returns it) | `not_prompted` | Step 4 silently |
   | `verdict: atomic` | Present `summary` to the user as a one-line note ("scope agent: \<summary\>"); `finalize` + `persist`. | `continue` | Step 4 |
   | `verdict: request_split` (continue anyway) | Present `summary`, each split (name, rationale, file count, estimated_new_loc, depends_on if any), and the `remaining_in_original` list; `finalize` + `persist`. | `continue` | Step 4 |
   | `verdict: request_split` (abort to split) | Same presentation as above; `finalize` + `persist` with `action: "terminal"` / `status: "scope_split_recommended"`. | `abort` | Exit `SCOPE_SPLIT_RECOMMENDED` → Step 5 (needs-attention comment with split recommendation; **move** files, do not duplicate). |
   | No verdict (substep 3 No path) | Set when user opts out of running the agent; no `verdict` is recorded. | `declined_agent` | Step 4 |

   **Non-interactive default for `request_split`:** abort with terminal status `SCOPE_SPLIT_RECOMMENDED` (the **Abort to split** path).

## Sidecar persistence contract

State is the source of truth. The sidecar at `<git-dir>/pr-loop/pr-scope.json` is a derived mirror used by `scripts/pr_scope_step.py` for fast plan-time inspection without re-parsing `state.json`. Persist order: **state first, then sidecar**, so a crash between writes leaves state authoritative and the sidecar regenerable.
