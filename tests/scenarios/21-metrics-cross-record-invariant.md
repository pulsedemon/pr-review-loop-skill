# Scenario 21: Metrics — per-iteration and terminal record schema + cross-record invariant

**Type:** CI-trusted traceability scenario for `.git/pr-loop/metrics.jsonl`. This documents the deterministic invariant already covered by `tests/bats/test_metrics_cross_record_invariant.bats`.

## Setup

Run the loop end-to-end against any PR that produces at least two iterations (e.g. scenario 13's adversary-catches-panel-miss fixture, run to terminal). After the run completes:

```bash
test -f .git/pr-loop/metrics.jsonl
ITER_LINES=$(grep -c '"kind":"iteration"' .git/pr-loop/metrics.jsonl)
TERM_LINES=$(grep -c '"kind":"terminal"'  .git/pr-loop/metrics.jsonl)
```

## Checks

1. **One `iteration` line per completed iteration.**

   ```bash
   STATE_ITER=$(jq .iteration .git/pr-loop/state.json)
   [ "$ITER_LINES" -eq "$STATE_ITER" ]
   ```

2. **Exactly one `terminal` line.**

   ```bash
   [ "$TERM_LINES" -eq 1 ]
   ```

3. **Knob values in terminal record match top-level state.**

   ```bash
   diff <(jq -r '.knobs.suggestion_promotion_threshold' < <(grep '"kind":"terminal"' .git/pr-loop/metrics.jsonl | tail -1)) \
        <(jq -r '.suggestion_promotion_threshold // 2' .git/pr-loop/state.json)
   ```

   Repeat for `adversary_promotion`, `adversary_solo_promotion`, `adversary_panel_visibility`, `max_iterations`, `max_new_loc`.

4. **Cross-record invariant: terminal totals equal sum of per-iteration counters.**

   For each pair (terminal totals key ↔ per-iteration counter):

   - `totals.promoted_multi_source` == sum of `promoted.multi_source` across all `iteration` lines.
   - `totals.promoted_adversary_endorsed` == sum of `promoted.adversary_endorsed`.
   - `totals.promoted_evidence_gated_solo_adversary` == sum of `promoted.evidence_gated_solo_adversary`.
   - `totals.evidence_verification_failed` == sum of `failed.evidence_verification`.

   Reference command (run once per pair, substituting the key):

   ```bash
   TERM=$(grep '"kind":"terminal"' .git/pr-loop/metrics.jsonl | tail -1 | jq '.totals.promoted_multi_source')
   ITER_SUM=$(grep '"kind":"iteration"' .git/pr-loop/metrics.jsonl | jq -s '[.[].promoted.multi_source] | add')
   [ "$TERM" -eq "$ITER_SUM" ]
   ```

   This is the invariant most likely to drift if a future change adds a `promotion_reason` and updates only one of the two writers.

## Pass criterion

All four checks succeed. A mismatch in check 4 indicates the per-iteration writer and the terminal writer have diverged on `promotion_reason` handling and must be reconciled before the metrics file can be used for tuning.

## Validation status

**Status:** `ci_trusted`
**Proof sources:** `tests/bats/test_metrics_cross_record_invariant.bats`
