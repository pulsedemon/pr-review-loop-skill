# Scenario 15: Second-instance sweep on schema permissiveness (Move B)

**Type:** Manual regression check for Move B as added to `reviewers/correctness.md`. Mirrors Copilot finding #3 from PR #5.

## Setup

Synthetic PR diff modifies `templates/state.schema.json` adding two new object subschemas (e.g. `history[].thing1[]` and `history[].thing2[]`), both with `properties` but no `required:` array — so empty objects validate against either. The persona ought to flag the missing `required:` once, name the pattern ("missing required on schema entry"), then sweep for the second instance.

## Run

Spawn `correctness.md` against the diff.

## Expected behavior

- Two findings raised against the schema file, each with `move_b_pattern: "missing required on schema entry"` (or close paraphrase).
- Each finding cites its own `thing1` / `thing2` line.

## Pass criteria

- Two distinct findings.
- Both carry a populated `move_b_pattern`.

## Failure modes worth recording

- Only one finding raised — Move B prompt isn't triggering the sweep; sharpen the "name the pattern, then grep the diff" language.
- Findings raised but missing `move_b_pattern` — the schema and persona prompt agree on the field name but the persona is forgetting to set it; add an explicit example in the prompt.

## Reminder

Do not wire into bats.

## Validation status

**Status:** `design_only`
**Missing evidence:** Add a dated validation run in this file for the Move B second-instance sweep behavior.
