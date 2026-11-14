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

## Validation status

**Status:** `design_only`
**Evidence:** see the partial observations in the 2026-10-28 and 2026-09-10 run blocks above.
**Missing evidence:** dated host runs covering delta-gate batching (check 2), conditional fallback (check 3), `cost_saver` model routing (check 5), and a run whose orchestrator did not write the reviewer-budget recipe.
