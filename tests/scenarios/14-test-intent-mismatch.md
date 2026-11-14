# Scenario 14: Test-intent mismatch (Move A)

**Type:** Manual regression check for Move A as carried by the `move_a` personas in `reviewers/personas.yaml`. Not wired into bats — LLM persona output is non-deterministic. Mirrors Copilot finding #2 from PR #5.

## Setup

Synthetic PR: `tests/match_findings.test.ts` adds a test named `it("rejects non-string summary")` whose body actually asserts `expect(() => match({summary: 42}, b)).toThrow(/line/)` — the assertion matches an integer-coercion error, not a string-type error.

Inputs to provide:

- PR body: "tightens matcher input validation; covers `summary` typing".
- Diff: only the test file changes.
- Changed-file list: `tests/match_findings.test.ts`.

## Run

Spawn `tests.md` (and separately `correctness.md`) as panel reviewers against the diff.

## Expected behavior

Either persona raises a `severity: blocker, scope: in_scope` finding with `finding_evidence` populated as:

- `file`: `tests/match_findings.test.ts`
- `line`: line number of the `expect(...).toThrow(...)` call
- `symbol`: `"rejects non-string summary"`
- `snippet`: ≤ 200 chars of the asserting line

## Pass criteria

- At least one Move A persona (`move_a: true` in `reviewers/personas.yaml`) raises the Move A finding.
- `finding_evidence` is populated and validates against `reviewers/output.schema.json`.
- The other persona's verdict does not contradict the finding (i.e. no spurious "approve with no findings" claiming the test is fine).

## Failure modes worth recording

- Persona raises the issue but does not populate `finding_evidence` — tighten the Move A prompt.
- Persona approves without flagging — Move A prompt isn't landing; consider a sharper imperative.

## Reminder

Do not wire into bats. Move A relies on LLM judgment of test-name-vs-body alignment; CI gates on this will flake.

## Validation status

**Status:** `design_only`
**Missing evidence:** Add a dated validation run in this file for the Move A persona behavior.
