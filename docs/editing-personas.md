# Editing the reviewer panel

The reviewer panel (panel personas + adversary + shared addendums) is declared
in `reviewers/personas.yaml`, the manifest. Treat it as the source of truth.

The procedure moves a persona applies are part of its prompt. Move C's body
lives canonically in [`procedure-moves.md`](procedure-moves.md) (move_c-true
personas link to it); Move A and Move B are inlined per-persona because
their wording is tuned to each persona's domain. See
[`procedure-moves.md`](procedure-moves.md) for the rationale.

## Add, remove, or rename a persona

1. Edit `reviewers/personas.yaml`. Each persona needs `name`, `file` (must
   equal `<name>.md`), and a one-line `description` (the bullet text shown
   in SKILL.md's "Reviewer personas" section). Use a YAML folded scalar
   (`>-`) for multi-sentence descriptions.
2. Run `scripts/regen.sh`. This regenerates the surfaces the
   manifest fully drives:
   - the SKILL.md "Reviewer personas" bullet list (via `cog`),
   - the SKILL.md §4b Move A / A.1 / B / C persona list bullets (via
     `cog`, `scripts/_move_c_bullet_for_cog.py`, from the `move_a`,
     `move_a1`, `move_b` and `move_c` flags),
   - the `reviewer` enum in `reviewers/output.schema.json` (via
     `scripts/regen_schema_enum.py`), and
   - panel-count phrases inside `<!-- regen:panel-count-* -->` regions
     across `SKILL.md`, `tests/scenarios/*.md`, and `reviewers/*.md`
     (via `scripts/regen_panel_counts.py`).
3. If you added a persona: create `reviewers/<name>.md`. If you removed
   one: delete its file. (The on-disk file set is intentionally a manual
   step; the sync test in `tests/bats/test_reviewer_enum_filesystem_sync.bats`
   catches mismatches.)
4. Run `bash tests/run.sh`. Any remaining failures name surfaces the
   generator does **not** manage, typically Move C body wording or
   per-persona prose tuned per domain. A move-membership failure means a
   `move_*` flag disagrees with the `## Procedure move` headings on disk;
   fix the flag or the persona file, not the generated bullet.

CI runs `scripts/regen-check.sh` (the `--check` companion to
`regen.sh`) in the cheap `validate` job, so a PR that forgot to
regenerate fails fast with a unified diff and the literal hint
`Run scripts/regen.sh ...`.

For the generator convention itself (cog vs. standalone, the contract every
generator must honor, how to add new surfaces), see
[`generators.md`](generators.md).

### What the generator manages vs not

| Surface | Managed by |
| --- | --- |
| SKILL.md "Reviewer personas" bullet list | `cog` (between the `<!--[[[cog ... ]]]-->` and `<!--[[[end]]]-->` markers in `SKILL.md`) |
| `reviewer.enum` in `reviewers/output.schema.json` | `scripts/regen_schema_enum.py` |
| `reviewers/<name>.md` on disk | **Manual.** Sync test only. |
| SKILL.md §4b Move A / A.1 / B / C persona list bullets | `cog` (via `scripts/_move_c_bullet_for_cog.py`, from the `move_a`/`move_a1`/`move_b`/`move_c` flags; markers in `SKILL.md`) |
| Panel-count phrases ("panel of N personas", "N personas total") inside `<!-- regen:panel-count-* -->` regions | `scripts/regen_panel_counts.py` (`--check`, `--write`, `--validate-markers`, `--validate-coverage`). The closure scan rejects new unwrapped numbered persona-count phrases unless they match an allowlist pattern in the generator. |
| Move A.1 `move_a1_pattern` sub-mechanic enum | `scripts/regen_move_a1_enum.py` (from `manifests/move-a1-enum.yaml`). Distinct from Move A.1 *membership*, which is panel-derived above. |
| Move C body in `docs/procedure-moves.md` | **Manual.** Orthogonal to the persona list. |

## Change the schema-constraint owner

Flip `owns_schema_constraint_blocker` on exactly one panel persona in
`reviewers/personas.yaml`. The Move C body lives canonically in
[`procedure-moves.md`](procedure-moves.md), so severity-rule edits land there
once. `tests/bats/test_move_c_drift_guard.bats` pins (a) the canonical doc's
canary phrases and the `Always` `suggestion` co-location on the
schema-constraint sub-bullet, and (b) every move_c persona's `## Procedure
move C` section linking to `docs/procedure-moves.md`. No multi-file edit
sync is required for the Move C body itself.

## What the manifest does NOT govern

Severity rules ("terminology drift = blocker, contract drift = suggestion") are
prose semantics, not structural facts. They are **currently unguarded by
automation**. Their canonical home depends on which procedure move owns them:

- Move C severity rules live canonically in
  [`procedure-moves.md`](procedure-moves.md); every `move_c: true` persona
  (declared in `reviewers/personas.yaml`) links to that doc, and `SKILL.md`
  §4b carries a one-line paraphrase pinned by
  `tests/bats/test_skill_move_c_persona_sync.bats`.
- Move A and Move B severity wording is still inlined per-persona in
  `reviewers/*.md` (their wording is tuned per persona), with the SKILL.md §4b
  bullets summarizing them.

If you change a Move C severity rule, edit `docs/procedure-moves.md` and check
that SKILL.md §4b still paraphrases it correctly. If you change a Move A or B
severity rule, search SKILL.md plus the relevant persona file manually; no
sync test will catch the drift.

## Severity-rule reachability on gated personas

`yagni` and `blind_spots` open with a gate that returns `verdict: approve` with
empty findings unless the diff adds a recognized surface (`blind_spots` also
runs Move A and Move C past its gate, so its early exit carries two further
conjuncts). The gate runs
**above** the severity sections, so a rule naming a surface the gate does not
list is dead on arrival: the persona exits before reading it. Nothing about the
output distinguishes that from a genuine "nothing to flag here".

So a severity bullet on those personas cites the gate surface id that admits it. A rule that
spans surfaces cites each one; the check requires at least one:

```markdown
- (c) Multi-level inheritance where composition would do
- (b)(c)(d) Plausibly over-abstracted code where reasonable people would disagree
```

`tests/bats/test_gate_rule_reachability.bats` fails when a bullet cites no id or
cites one the gate does not define. The id source differs per persona (`yagni`
numbers its gate bullets; `blind_spots` uses `### (x)` headings under
`## Categories you cover`), so the test declares it per persona.

If no gate surface admits a rule you want to add, the rule is unreachable.
Check the intended applicability before adding a surface, since that broadens
which changes the persona reviews.

Two limits worth knowing. The check sees only bullets under
`## What to flag as ...`, so severity rules carried by procedure moves are
invisible to it. And it catches unreachable, not mis-attributed: a tag that is
live but names the wrong surface passes.

The first limit has a corollary. A gated persona that also carries procedure
moves must carve the **independently triggered** ones out of its gate in prose,
or the prompt instructs two different outputs on the same diff. Move B is the
exception that needs no conjunct: it fires only after a finding exists, so the
early-exit path never reaches it. `blind_spots` is
the worked example for two moves: its early exit names Move A and Move C as
conjuncts it does not override (`reviewers/blind_spots.md` `## Rules`).
`requirements` is the older single-move example, carving Move C out of its gate
at `## Applicability gate`. Both are pinned by
`tests/bats/test_applicability_gate_text.bats`.

`type_design` is exempt. Its gate is a single condition ("at least one type
definition") whose bullets are language syntaxes rather than distinct surfaces,
so any type rule is admitted by construction and a tag would disambiguate
nothing. Its blocker section restates the gate instead, which the same test
pins.

## Evaluating reviewer changes

Verify code fixes with reproducible checks, focused regression coverage, and
review. The [recall harness](../tools/recall-harness/README.md) is an optional
evaluation tool. Shipping does not require a generated report, a minimum
number of labeled findings, or an owner override.

For persona prompts or reviewer defaults, comparative replay can help assess
useful findings, false positives, and retained catches. Choose examples that
exercise the changed behavior; the existing corpus can supply relevant cases.
When citing results, identify the reviewed revisions and findings, and state
the limits of the evidence. Use the [labeling protocol](../tools/recall-harness/label.md)
to keep corpus judgments reproducible.

## Mutation-test the contract

`tests/bats/test_manifest_drift_localization.bats` swaps a fixture manifest
with an extra `phantom` persona into place, then runs every dependent sync
test and asserts each fails with a message naming a specific surface. If the
acceptance criterion ever regresses (one manifest edit no longer surfaces
every drifted surface by name), that test catches it.
