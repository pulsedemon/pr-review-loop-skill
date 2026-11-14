# Scenario 16: Cross-doc paraphrase drift (Move C)

**Type:** Manual regression check for Move C as added to `reviewers/readability.md` and `reviewers/requirements.md`. Mirrors Copilot finding #5 from PR #5.

## Setup

Synthetic PR diff modifies SKILL.md §4c to state the matcher uses Jaccard overlap ≥ 0.6, AND modifies README.md to claim the matcher uses "cosine similarity ≥ 0.7". The doc paraphrase contradicts the spec wording.

## Run

Spawn `readability.md` (and separately `requirements.md`) against the diff.

## Expected behavior

At least one of the two raises a `severity: blocker, scope: in_scope` finding on the README line:

- `summary`: README paraphrases SKILL.md matcher rule incorrectly (cosine 0.7 vs. Jaccard 0.6).
- `detail`: cites both the README line and the SKILL.md §4c rule.

## Pass criteria

- Either persona flags the drift as a blocker.
- The finding cites both files.

## Failure modes worth recording

- Both personas approve — Move C prompt isn't landing; tighten "compare paraphrase to actual spec wording".
- Persona flags it but `scope: out_of_scope` — emphasize that paraphrase drift is in-scope when both files are touched.

## Reminder

Do not wire into bats.

## Validation status

**Status:** `design_only`
**Missing evidence:** Add a dated validation run in this file for the Move C cross-doc drift behavior.
