# Scenario 22: SKILL split — docs anchors and drift guard

**Type:** Manual regression check for the SKILL.md → `docs/synthesis.md` + `docs/adversary.md` split.

## Setup

No PR fixture. Run against the repository at HEAD.

## Checks

1. **`SKILL.md` does not contain the matcher rule literal.**

   ```bash
   grep -c "token_overlap >= 0.6" SKILL.md
   ```

   Expected: `0`.

2. **`docs/synthesis.md` exists with the three expected anchors.**

   ```bash
   grep -c '^## Matcher$\|^## Promotion paths$\|^## Demotion recording$' docs/synthesis.md
   ```

   Expected: `3`.

3. **`docs/adversary.md` exists and links back to synthesis anchors.**

   ```bash
   grep -c "synthesis.md#matcher\|synthesis.md#promotion-paths" docs/adversary.md
   ```

   Expected: at least `2`.

4. **`tests/run.sh` runs the drift guard.**

   ```bash
   grep -cE "token_overlap\[\[:space:\]\]\*>=\?" tests/run.sh
   ```

   Expected: `1` (the guard's `grep -qE` pattern).

   The guard matches the threshold as a regex, not a literal, so it catches
   spacing and `0.6`/`.60` variants that a fixed-string grep would miss. Asserting
   the literal `token_overlap >= 0.6` here would pass only by accident and rots
   the moment the pattern is retuned.

## Pass criterion

All four checks return their expected values. If any fail, the split has drifted and Phase A must be re-applied before Phases B or C can land.

## Validation status

**Status:** `ci_trusted`
**Proof sources:** `tests/bats/test_skill_split_anchors.bats` pins all four checks and additionally plants the matcher literal to prove the `tests/run.sh` guard still rejects a violation.
