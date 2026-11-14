# Adversary pass: Mechanics

This document owns the mechanics for the §4d.0 adversarial pass and the §4d.0.5 re-synthesis step. `SKILL.md` keeps only the inputs/outputs/branches/knobs contract; everything below moved here from the original SKILL.

## Adversary inputs (§4d.0)

Spawn one subagent using `reviewers/adversary.md`. Inputs in the order the prompt presents them:

1. PR metadata, body, linked tickets.
2. The diff.
3. The changed-file list, plus the iteration's head SHA.
4. The `shallow_review` flag list from §4c.
5. **Panel data**, in the form configured by `adversary_panel_visibility`:
   - `"blind"`: omit this item entirely.
   - `"verdicts_only"`: per-reviewer `{name, verdict}` pairs only. Not the findings or reasoning.
   - `"full"` (default): raw reviewer JSON including findings. Default raised from `"verdicts_only"` to `"full"` in the recall-improvements PR (2026-05); see `SKILL.md` Inputs for the rationale.

The list stays at five items. The adversary does NOT receive `human_comments`: that block is panel-only by design (see `SKILL.md` §4a / §4b).

the adversary returns JSON matching `reviewers/output.schema.json` with `reviewer: "adversary"`. validate it with `scripts/validate_reviewer_output.py --reviewer adversary`.

## Failure handling

missing or invalid adversary output records `adversary_error`. on the approval
path, record the incomplete iteration and exit `REVIEW_INCOMPLETE`. an approval
that fails the [final read-evidence requirement](exit-conditions.md#required-reviews-at-completion)
or a response with no findings and a non-approval verdict records the
actual response and takes the same exit. none of these failures creates a finding
or enters the edit phase.

on the forced path, retain real panel blockers and record the adversary result
or error. the existing forced-run cap still applies. a later approval requires
a fresh valid final adversary response.

## Cap source of truth

<!-- regen:adversary-caps:start -->
The cap is 2 (see ADVERSARY_CAP in templates/state.schema.json).
<!-- regen:adversary-caps:end -->

The cap value is generator-managed: edit `cap` in `manifests/adversary-caps.yaml`, then run `scripts/regen.sh` to propagate to all three mirrors (the schema maxima on `shallow_adversary_runs` and `shallow_approval_adversary_runs`, the `scripts/_adversary_caps.sh` preset-guard + `readonly`, and the cap sentence above). The schema remains the machine-enforced contract; shell scripts refer to `ADVERSARY_CAP`, and Markdown surfaces (`SKILL.md`, `CLAUDE.md`) refer to "the cap" or "its cap." Frozen historical specs under `docs/superpowers/` and the recall-harness report at `tools/recall-harness/REPORT.md` may still name the literal: they are excluded from the drift guard by design. Manual test fixtures under `tests/scenarios/` may name the literal directly because they encode specific cap-boundary expectations. At runtime, `state_init.sh` cross-checks `ADVERSARY_CAP` against the schema `maximum` for both counter fields and prints both values to stderr on mismatch (exit 6). The drift guard in `tests/run.sh` enforces the canonical-home rule for contract prose.

## Forced-path counter

On the forced path (entered from `blockers > 0` with `shallow_review` non-empty), increment `shallow_adversary_runs` by 1 in state immediately after the adversary runs (whether it returned findings, returned none, or errored). The counter is loop-scoped, capped at `ADVERSARY_CAP` (gate in `SKILL.md` §4d), and never decrements.

## Branching after §4d.0 runs

after validation, pipe the actual response through `scripts/flag_shallow_reviews.py`
alongside the panel personas and persist the resulting `shallow_review` list.
apply the failure handling above before routing a successful review:

- no findings: record `history[].adversary` and continue to §4d.1 on the approval
  path, or §4e with the existing blockers on the forced path.
- findings: record `history[].adversary` and continue to §4d.0.5.

the adversary runs at most once per iteration on either path. new runs do not
write `shallow_approval_adversary_runs`, `shallow_blocker`, or
`adversary_shallow_giveup`; the schema retains them for historical state reads.

## §4d.0.5 Re-synthesize after adversary

Only runs when §4d.0 returned findings. Invoke `scripts/promote_findings.py` once, passing the panel and adversary finding lists separately so the script handles both the matcher merge and the three promotion paths:

```bash
jq --argjson panel "$panel_findings" --argjson adv "$adversary_findings" --argjson dem "$demoted" \
  '{panel_findings:$panel, adversary_findings:$adv, suggestion_promotion_threshold, adversary_promotion, adversary_solo_promotion, demoted:$dem}' \
  "$(git rev-parse --git-dir)/pr-loop/state.json" \
  | python3 "$SKILL_ROOT/scripts/promote_findings.py"
```

The script:

1. **Merges adversary findings into the panel set** using the matcher rule from [`docs/synthesis.md#matcher`](synthesis.md#matcher), only when their scopes agree. Matched panel findings get `adversary` unioned into their `source_reviewers`. Scope disagreements and unmatched adversary findings stay separate, preserving each finding's disposition.
2. **Applies the three promotion paths** defined in [`docs/synthesis.md#promotion-paths`](synthesis.md#promotion-paths). Precedence and disable knobs are owned by the synthesis doc; do not duplicate them here.

An explicit in-scope adversary blocker matched to a panel suggestion or nit keeps its severity and diagnostic payload. The merge retains the blocker's detail, fix, and evidence and unions reviewer provenance. This does not depend on suggestion-promotion settings and creates no promotion provenance. Scope disagreements remain separate.

### Evidence-gate verification (evidence-gated solo-adversary path)

When a finding qualifies for the evidence-gated path, `promote_findings.py` verifies `finding_evidence` against the working tree:

- `finding_evidence.file` exists.
- `finding_evidence.line` is within the file's line count (empty files always fail).
- `finding_evidence.symbol`, if present, appears in the file.
- `finding_evidence.snippet`, if present, appears in the file.

On success: the finding moves to `blockers[]` and a provenance entry lands in `addressed[]`. On any verification failure: the finding lands in `deferred[]` as a provenance object with `promotion_reason: "evidence_verification_failed"` (the failure reason is appended to the summary).

The `demoted[]` array driving the panelist-objection check is the one this iteration's §4c synthesizer recorded ([demotion recording](synthesis.md#demotion-recording)). Absence/empty is treated as "no panelist objected": a soft contract on the synthesizer's recordkeeping.

## Post-merge blocker routing

If the merged blocker set is now > 0:

- Approval path: continue to §4e (the loop now has blockers to fix this iteration, even though the panel returned zero).
- Forced path: continue to §4e with the merged blocker list.

If the merged blocker set is still 0:

- Approval path: continue to §4d.1.
- Forced path: continue to §4e using the existing (pre-merge) blocker list. (Forced-path adversary `suggestion`s are recorded in history but do not block; the loop already has blockers to address this iteration.)

## Adversary knobs

### `adversary_promotion` (default `false`)

Whether an adversary endorsement promotes a matched panel suggestion, with `promotion_reason: "adversary_endorsed"`, regardless of `suggestion_promotion_threshold`. Setting it to `false` disables that promotion path and keeps the adversary running. Explicit blockers follow the merge behavior above. Earlier versions also let this switch suppress an adversary blocker matched to a nit; the switch now controls suggestion endorsement only.

### `adversary_solo_promotion` (default `false`)

Whether the synthesizer promotes a solo-adversary suggestion after the evidence and objection checks above. A valid source anchor verifies where the finding points; it does not prove the claimed defect. With this switch off, the suggestion and its evidence remain available without promotion.

### `adversary_panel_visibility` (default `"full"`)

What the adversary in §4d.0 sees of the panel's outputs. Values:

- `"blind"`: no panel data.
- `"verdicts_only"`: per-reviewer verdict pairs only (name + verdict, no findings or reasoning).
- `"full"`: raw reviewer JSON including findings and reasoning.

Default raised from `"verdicts_only"` to `"full"` in the recall-improvements PR (2026-05). The existing §4d.0.5 evidence gate and endorsement-match rule constrain promotion noise, and `"full"` improves the adversary's chance of catching what the panel obscured by approving. Set back to `"verdicts_only"` if a measured false-positive uptick is attributed to the change.
