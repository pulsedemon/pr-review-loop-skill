# Synthesis — Mechanics

This document owns the mechanics for the §4c synthesis step. `SKILL.md` keeps only the inputs/outputs/branches/knobs contract for §4c; everything below moved here from the original SKILL.

## Matcher

Findings from different reviewers are deduped using this rule:

> `same_file AND abs(line_a - line_b) <= 5 AND token_overlap(summary_a, summary_b) >= 0.6`

`token_overlap` is Jaccard similarity over lowercased word-sets with English stop-word filtering. The shared implementation lives in `scripts/finding_matcher.py`; `scripts/match_findings.py` exposes the CLI contract, and `scripts/promote_findings.py` uses the same matcher for adversary/panel merge logic. Findings without `file` + `line` are not deduped against anything — they pass through as-is.

`finding_matcher.py` also exports `token_containment`, a scorer for comparing summaries of very different lengths. §4c does not use it and must not: two panel findings are the same length and register, and containment merges distinct findings that share vocabulary. It exists for the offline recall harness, which pairs a terse loop finding against a much longer bot comment. `is_match` takes the scorer and its bounds as keyword-only arguments defaulting to the rule above, so a two-argument call is exactly §4c.

## Promotion paths

After dedupe and `out_of_scope` drop, the synthesizer hands the remaining findings to `scripts/promote_findings.py`. The script owns all three promotion paths and returns the partitioned `{blockers, suggestions, nits, addressed, deferred}` set:

```bash
jq -n --argjson f "$findings" --argjson dem "$demoted" \
  '{findings:$f, suggestion_promotion_threshold:'"$suggestion_promotion_threshold"', adversary_promotion:'"$adversary_promotion"', adversary_solo_promotion:'"$adversary_solo_promotion"', demoted:$dem}' \
  | python3 "$SKILL_ROOT/scripts/promote_findings.py"
```

- Exit 0: use the partitioned set as this iteration's action plan.
- Exit 2: synthesizer error — surface to the harness (treat as `SETUP_ERROR`).

The three promotion paths, applied in order per `suggestion`:

1. **Adversary endorsement** (`promotion_reason: "adversary_endorsed"`, `promoted_by: "adversary"`): `"adversary" in source_reviewers` AND `len(set(source_reviewers)) >= 2`. Promotes regardless of `suggestion_promotion_threshold`. Disabled when `adversary_promotion=false`.
2. **Multi-source** (`promotion_reason: "multi_source"`, `promoted_by: "multi-persona"`): `len(set(source_reviewers)) >= suggestion_promotion_threshold > 0`.
3. **Evidence-gated solo-adversary** (`promotion_reason: "evidence_gated_solo_adversary"`, `promoted_by: "adversary"`): `source_reviewers == ["adversary"]` AND severity `suggestion`, scope `in_scope`, `finding_evidence` present and well-formed, no entry in this iteration's `demoted[]` with same `file` and `abs(line - finding_evidence.line) <= 5`. On promotion, the script verifies the evidence against the working tree (file exists, line in range, symbol/snippet present). On any verification failure: the finding lands in `deferred[]` with `promotion_reason: "evidence_verification_failed"`. Disabled when `adversary_solo_promotion=false`.

What does NOT get promoted:

- `out_of_scope` findings.
- `nits`.
- A single non-adversary persona's `suggestion`, even if it looks strong.
- Findings without both `file` and `line` — the matcher needs them.

That `nits` line is why the tier exists. `partition()` checks `nit` before every
promotion path, so a nit stays a nit no matter how many personas raise it, while
a `suggestion` two personas both surface promotes to `blocker` at the default
`suggestion_promotion_threshold`. A persona with something true but trivial to
say has `nit` for it, and picking it is a decision not to let agreement escalate
a triviality into a required change. The one thing that outranks a nit is the
merge itself: an in_scope adversary `blocker` matched to a panel nit keeps its
blocker verdict (see [`docs/adversary.md#adversary-knobs`](adversary.md#adversary-knobs)).

Emitted by `tests` and `comments` today. Both summary templates render a nits
section; without one an emitted nit is counted in `n_nits` and then never shown.
The same holds for the `suggestions[]` partition — an in-scope suggestion no
promotion path picked up — which is why both templates carry a suggestions
section too. Neither is rendered from one iteration's partitions: a delta-gated
panel leaves earlier ones unrevisited, so Step 5 accumulates both across
`history[]` (see
[`docs/step5-summary.md`](step5-summary.md#carrying-open-suggestions-and-nits)).

Multi-source counting is **per-iteration**: `promote_findings.py` counts `source_reviewers` within a single call and never reads `history[]`. A delta-gated partial panel (see [`docs/delta-gate.md`](delta-gate.md)) therefore just feeds fewer findings into one `partition()` call — it does not change the promotion math.

## Demotion recording

When the synthesizer drops a finding as not-a-problem or demotes a `blocker` to `suggestion`/`nit`, it MUST append a record to this iteration's `demoted[]`:

```json
{"file": "src/a.ts", "line": 42, "summary": "unchecked json.loads", "reviewer": "security", "reason": "not_a_problem", "note": "input is controlled by caller"}
```

`reason` is `"not_a_problem"` (dropped entirely) or `"synthesis_demoted"` (downgraded blocker → suggestion or blocker → nit). `note` is optional but recommended. Persist `demoted[]` to `history[].demoted[]` at iteration end alongside `findings`, `addressed`, `deferred`. §4d.0.5 reads it to detect panelist objection — an absent or empty `demoted[]` is treated as "no panelist objected", so a forgotten record may let an unfounded adversary suggestion auto-promote.

## Synthesis knobs

### `suggestion_promotion_threshold` (default `2`)

Number of distinct reviewer outputs that must surface the same `in_scope: suggestion` finding (matched per the matcher rule above) for the synthesizer to promote it to `blocker`. Set to `0` to disable multi-persona promotion entirely. The default of `2` is a starting point, intended to be tuned after observing real-PR data — too low and harmless duplicate suggestions blow up into blockers, too high and a finding two reviewers both see independently never gets escalated.

The threshold only governs the multi-source path. Adversary endorsement (§4d.0.5) and the evidence-gated solo-adversary path use independent gates owned by the adversary knobs in [`docs/adversary.md`](adversary.md#adversary-knobs).
