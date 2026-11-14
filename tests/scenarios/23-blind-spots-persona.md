# Scenario 23: blind_spots persona end-to-end

**Type:** Manual end-to-end check for the new B2 persona.

## Setup

A test PR (real or fixture) with:

- A new async function in `src/handler.ts` that reads a shared module-level cache, awaits a network call, then writes back to the cache (concurrency category (a)).
- A new error path in `src/parser.ts` that `throw`s `new ParseError(...)` from a public function, with NO test exercising the throw and NO try/catch in callers (error-path category (b)).
- A new env var `EXTERNAL_API_URL` consumed by a new `fetch()` call in `src/api-client.ts` with no timeout argument (config/env category (c)).

## Checks

1. **Persona spawns.** Run the loop in dry-run on the test PR. Confirm `blind_spots` appears in the per-reviewer subagent fan-out (one entry alongside the other panel personas listed under SKILL.md "Reviewer personas").

2. **Concurrency hazard flagged as blocker.** The persona's JSON output contains a `blocker, in_scope` finding citing `src/handler.ts` referencing the cache read/await/write pattern.

3. **Error-path flagged as blocker.** The persona's JSON output contains a `blocker, in_scope` finding citing `src/parser.ts` line of the `throw`, referencing missing test AND missing handler.

4. **Timeout-less external call flagged as blocker.** The persona's JSON output contains a `blocker, in_scope` finding citing `src/api-client.ts` line of the `fetch()` call, referencing missing timeout.

5. **Evidence populated.** The persona's `evidence.files_read` includes all three of `src/handler.ts`, `src/parser.ts`, `src/api-client.ts`. (Otherwise `flag_shallow_reviews.py` would flag it.)

6. **No out-of-scope findings.** No finding references untouched files. No finding is a style/naming/refactor.

7. **Empty-diff case.** Re-run on a PR satisfying all three early-exit conjuncts: none of the three patterns, no new or modified test, and not both a doc and a spec (e.g. a one-line value change in a single source file). The persona returns `verdict: approve, findings: []` with populated `evidence.files_read`. It does NOT invent findings.

8. **Move C survives the early exit.** re-run on a PR with none of the three patterns and no test touched, whose diff edits both a spec and a doc that paraphrases it, with a deliberate algorithm mismatch planted in the doc. the spec says the matcher uses Jaccard overlap at least 0.6, while the doc says it uses cosine similarity at least 0.7. this is terminology drift, the Move C sub-rule whose severity is unconditionally `blocker` (`docs/procedure-moves.md`). contract drift is `suggestion` unless the doc is the contract, and schema-constraint drift is always `suggestion`. the persona does not early-exit: it runs Move C and returns a `blocker` citing both sides. a `verdict: approve, findings: []` here is the #121 regression because the gate swallowed a mandatory move. a consistent doc/spec pair is not a valid fixture for this check because it can legitimately approve, so it cannot tell the regression from correct behavior.

9. **Move A survives the early exit.** re-run on a PR with none of the three patterns and without both a doc and a spec touched, whose diff modifies only a test. reuse the intent-mismatch fixture from `tests/scenarios/14-test-intent-mismatch.md`: the test is named `rejects non-string summary`, but its assertion matches an integer-coercion line error rather than a string-type error. the persona does not early-exit: it runs Move A and returns a `blocker` with `finding_evidence` on the mismatched assertion. a `verdict: approve, findings: []` here is the #121 regression because the gate swallowed a mandatory move.

## Pass criterion

all 9 checks observed in the loop's per-iteration logs / final summary comment.

## Notes

This scenario is not automated because it depends on subagent LLM behavior. Run it manually after any change to `reviewers/blind_spots.md` or to the loop's subagent fan-out.

## Validation status

**Status:** `design_only`
**Missing evidence:** add a dated end-to-end validation run for the `blind_spots` persona behavior, including check 8 (Move C runs past the early exit) and check 9 (Move A runs past the early exit).
