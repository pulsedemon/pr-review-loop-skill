# Delta-gated reviewer panel

Canonical mechanics for §4a.1 of `SKILL.md`. SKILL.md carries only the
invocation and branch points; the prompt body, fail-open rules, and rationale
live here.

## What it does

On iterations ≥ 2, the loop runs only the reviewer personas that plausibly
have something to say, instead of the full §4b panel every iteration. A
persona runs this iteration if any of these hold:

- it raised a **blocker** last iteration, including a promoted suggestion recorded in provenance (open-blocker carryover), or
- the **delta-gate pre-pass** judged it relevant to the prior commit's delta, or
- it failed open (its gate result was missing/untrustworthy), or
- this is iteration 1, or the forced pre-approval full sweep, or
  `delta_gate=false` — all of which run the full panel unconditionally.

Selection is computed by `scripts/select_panel.py` (deterministic, unit-tested);
the only LLM work added is the gate pre-pass subagents.

## §4a.1 — delta-gate pre-pass (iterations ≥ 2, `delta_gate=true`)

1. **Compute the delta.** `git diff <prev.head_sha_before>..<prev.head_sha_after>`
   where `prev` is `history[N-1]`. SKILL.md §4g commits exactly once per
   iteration and `safe_push.sh` refuses force-pushes, so the two SHAs bracket
   exactly one commit. Empty range (`before == after`) ⇒ no personas are
   delta-relevant.
2. **Candidates.** `candidates = panel \ open-blocker personas`. Open-blocker
   personas are already required and skip the gate. `panel` is the effective
   panel after `approvers_required`.
3. **Cap.** If `len(candidates) < delta_gate_min_candidates` (default 4), skip
   the pre-pass; all candidates run.
4. **Spawn one gate subagent per candidate, in parallel.** Launch the pre-pass as
   one batch: one subagent call per candidate, all inside a single
   message, and await results only after the last
   launch. When the host cannot spawn subagents in parallel, the gate launches
   run sequentially, but keep outputs independent until validation/selection.
   Each
   receives only the persona name, its one-line domain summary from
   `reviewers/personas.yaml` (`description`) — not the full persona prompt —
   the delta diff, and the delta's changed-file list. Prompt body below.
5. **Validate.** Pipe each subagent's output through
   `scripts/validate_gate_output.py --reviewer <dispatched-name>`. Exit 0 ⇒ trust
   it. Exit 2, a timeout, or a missing response ⇒ discard it.
6. **Select.** Pass `panel`, `iteration`, `delta_gate`,
   `delta_gate_min_candidates`, `prev_history` (the `history[N-1]` entry), and
   `gate_results` (only the validated, trusted outputs) to
   `scripts/select_panel.py`. Any candidate absent from `gate_results` fails
   open — it runs, and is recorded under `gate_fail_open`.
7. **Record.** Persist the script's `panel_selection` object to this
   iteration's `history[]` entry. Run §4b for the personas in `ran` only.
   An empty `ran` is valid: when every candidate's gate says `false` (or the
   delta is empty), §4b spawns no reviewers, synthesis yields `blockers == 0`,
   and the §4d forced pre-approval full sweep re-runs the whole panel before
   the loop can approve — so nothing is missed.

## Gate prompt body

> You are the relevance gate for the `<NAME>` reviewer persona. Its domain:
> `<ONE-LINE DESCRIPTION>`.
>
> Below is the *delta* — the diff a single commit added since the last review
> iteration. Answer one question: does this delta contain anything in your
> persona's domain that would be worth a full review pass?
>
> Answer `false` only if you are confident the delta contains nothing in your
> domain. If in doubt, answer `true`. A wrong `false` silently drops a review;
> a wrong `true` only costs one extra review pass.
>
> Return strict JSON: `{"reviewer": "<NAME>", "relevant": true|false,
> "reason": "<one line>"}`. Nothing else.

## Fail-open — the core safety property

The gate may only ever *remove* work on a clean, confident `false`. Every
other outcome runs the persona:

- gate subagent errors, times out, or never responds ⇒ run the persona;
- output fails `validate_gate_output.py` ⇒ run the persona;
- candidate has no entry in `gate_results` ⇒ run the persona.

A skipped persona is therefore always the result of a persona explicitly and
validly saying "nothing for me here."

## Forced pre-approval full sweep

The first iteration whose delta-gated panel reaches `blockers == 0` does **not**
proceed straight to §4d.0 if any persona was skipped. It first re-runs the
**full** panel (`select_panel.py` is bypassed; every persona runs). Only after
a full panel produces `blockers == 0` does the loop continue to the adversary /
CI / `SUCCESS` path. The sweep sets `forced_full_sweep: true` on the history
entry. It is part of the same iteration N — no counter increment, no extra
`history[]` entry. If it surfaces new blockers, the post-sweep set becomes
iteration N's recorded blocker set and §4d is re-entered from the top against
it: the `NO_PROGRESS` and `TESTS_REGRESSED` exit rows still apply, so a sweep
that merely re-finds the previous iteration's blockers exits `NO_PROGRESS`
rather than churning into another fix attempt.

## Knobs

- `delta_gate` (default `true`): master switch. `false` ⇒ full panel every
  iteration (status quo).
- `delta_gate_min_candidates` (default `4`): below this many candidates, skip
  the gate pre-pass and run all candidates directly.

## Break-even — why the cap defaults to 4

A gate subagent and a full review are both subagent spawns, so the gate pays
off only when one gate call is far cheaper than the full review it may skip.
A gate call carries a one-line domain summary (no persona prompt), the small
delta diff, and a fixed question; it does no file reads, no caller/test greps,
and no procedure Moves A/A.1/B/C. A full review carries the whole persona
prompt, the full cumulative diff, mandatory file reads, multiple greps, and the
per-persona moves — empirically a much larger footprint. If a gate call costs
`g` and a full review costs `R` with `R ≫ g`, gating `k` candidates and
skipping fraction `s` nets `k·g` spent to save `s·k·R`; positive whenever
`s > g/R`. With `R` an order of magnitude over `g`, even a 1-in-10 skip rate
wins once `k` is non-trivial. `delta_gate_min_candidates` guards the small-`k`
corner where the absolute saving is not worth the extra orchestration step.
Tune it after observing real-PR `panel_selection` data, like
`suggestion_promotion_threshold`.

## Interaction notes

- **Synthesis.** Multi-source promotion is within-iteration only
  (`promote_findings.py` never reads `history[]`); a partial panel just feeds
  fewer findings into `partition()`. See `docs/synthesis.md`.
- **Shallow-review detection.** Skipped personas produce no output and are
  absent from the synthesis input array; `flag_shallow_reviews.py` only sees
  personas that ran.
- **`NO_PROGRESS`.** A persona with an open blocker is always re-run, so a
  blocker can never vanish via skipping.
- **Adversary.** Unchanged; the forced pre-approval sweep runs before §4d.0, so
  the adversary always sees a fully-reviewed state.
- **Move-bearing personas.** A persona's procedure moves are mandatory only on
  iterations where it runs, so a skipped persona defers every move it carries
  rather than discharging it. That is every move, not just the diff-triggered
  ones: Move B is unreachable on a gate's early-exit path because it needs a
  prior finding, but a skipped persona raises no finding at all, so its Move B
  is deferred alongside Move A, Move A.1, and Move C. The gate subagent cannot
  act on that duty: it gets the persona name and its one-line `description`.
  Only `blind_spots` mentions moves at all, generically, and no description
  ties one to the diff shape that triggers it. A Move C trigger on
  `readability` ("naming, cohesion, obvious dead code") reads as out-of-domain
  to it.
  What recovers the finding is the forced full sweep. The guarantee is exactly
  its trigger: an iteration that reaches `blockers == 0` with a persona skipped
  sweeps before it can approve, so nothing is stranded on that path. Any exit
  taken before that point strands whatever was deferred, whether it leaves from
  §4c (`DRY_RUN_COMPLETE`), from the `blockers > 0` path through §4e–§4h
  (`TESTS_REGRESSED`, a §4f `SETUP_ERROR`, `EXTERNAL_PUSH`), or from §4d's own
  exit rows (`MAX_ITERATIONS`, `NO_PROGRESS`). Reason from the trigger rather
  than from a list of statuses: several are multi-sourced, and the same status
  can land on either side of the sweep depending on where it fired.
- **Step 5 summary.** Suggestions and nits have no carryover rule of their own —
  only blockers do — so a skipped persona leaves its earlier ones unrevisited.
  Step 5 accumulates them from `history[]` rather than rendering the last
  iteration's partitions; see
  [`docs/step5-summary.md`](step5-summary.md#carrying-open-suggestions-and-nits).
