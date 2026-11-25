# Tests for pr-review-loop

This directory has two layers of test coverage:

- **`bats/`**: automated bats tests for the helper scripts in `scripts/`. Run with `bash tests/run.sh`. Requires [bats-core](https://github.com/bats-core/bats-core) (`brew install bats-core` on macOS, `apt-get install -y bats` on Ubuntu), `python3` with the `pyyaml` and `jsonschema` packages (`pip install pyyaml jsonschema`), plus `jq` and `git`. Wired into CI in `.github/workflows/ci.yml`.
- **`scenarios/`**: pressure-test fixtures for the agent-level behavior of the loop. `tests/scenarios/manifest.yaml` is the source of truth for each scenario's validation tier: `ci_trusted`, `manual_validated`, or `design_only`. The scenario files remain the human-readable fixtures and traceability docs.

The two layers are complementary: bats covers the deterministic plumbing, scenarios cover the agent's discipline.

## Pressure-test fixtures (scenarios/)

These scenarios let you verify the skill under pressure before shipping changes to
it. They follow the TDD-for-skills methodology from `superpowers:writing-skills`:

1. **RED**: run the scenario against a subagent **without** the skill in scope.
   Write down the rationalizations it produces verbatim under
   `Baseline behavior (no skill)` in that scenario file.
2. **GREEN**: run the same scenario with `SKILL.md` in scope. Confirm the
   subagent now behaves per `With skill (target behavior)`.
3. **REFACTOR**: if the subagent still rationalizes its way out under pressure,
   update `SKILL.md` (typically the `Rationalizations to reject` table or the
   `Red flags` list), re-run, and record the final pass.

Scenario files come in two shapes. The RED/GREEN/REFACTOR cycle above applies
to the first; the second skips RED because there is no meaningful "without the
skill" comparator for a persona-prompt or repo-state contract.

**Pressure fixtures** (`01`–`12`) open with `**Pressure type:**` and carry:

- **Pressure type**: what kind of pressure it applies (approval, scope,
  sunk-cost, force-push, draft).
- **Setup**: the fixture: PR metadata, simulated reviewer output, or a fake CI
  failure. Copy it verbatim into the subagent's prompt.
- **Baseline behavior (no skill)**: filled in after the first RED run. Capture
  exact verbatim rationalizations; they are the raw material for the
  rationalization table in `SKILL.md`.
- **With skill (target behavior)**: the expected compliant outcome.

**Regression checks** open with `**Type:**` and have no baseline
section. They pin a persona's output, an orchestration property, or repo state,
using `Setup` plus either `Expected behavior` / `Pass criteria` or a numbered
`Checks` list. Several carry a `## Reminder` forbidding bats automation because
they gate on non-deterministic LLM output.

Every scenario, both shapes, ends with a `## Validation status` section. That
section is machine-checked against the manifest: see the tiers below.

## Scenario validation tiers

- **`ci_trusted`**: the scenario's core contract is already covered by deterministic repo tests. The scenario file acts as a traceability doc and must cite its proof source path(s) from `tests/scenarios/manifest.yaml`.
- **`manual_validated`**: a dated passing host run is recorded in the scenario file. Use this tier when the repo can pin the contract text but cannot deterministically prove the runtime behavior.
- **`design_only`**: the scenario is still a design fixture. It documents the intended contract, but there is not yet a dated passing manual run or sufficient deterministic automation to trust it as validated. Recorded failed or partial observations still belong here until the contract is actually validated.

Check the manifest-derived tier map with:

```bash
python3 scripts/scenario_manifest.py --list tier-map
```

Validate the embedded status sections with:

```bash
bats tests/bats/test_scenario_validation_sync.bats
```

## Running a scenario

To run a manual scenario by hand:

1. Spawn a subagent with the scenario's `Setup` as its prompt. Do **not** include
   `SKILL.md` yet: this is the RED run.
2. Record what the subagent does into `Baseline behavior (no skill)`. Write down
   the verbatim rationalizations, not a paraphrase.
3. Spawn a second subagent with the same `Setup` plus `SKILL.md` and the
   reviewer personas in scope. Confirm the behavior matches
   `With skill (target behavior)`.
4. If it doesn't, find which specific loophole the subagent used, plug it in
   `SKILL.md`, and re-run.

## Scenarios

| # | File | Focus | Tier |
| --- | --- | --- | --- |
| 1 | `tests/scenarios/01-approval-pressure.md` | Approval pressure | `manual_validated` |
| 2 | `tests/scenarios/02-ci-out-of-scope.md` | CI failure looks out of scope | `manual_validated` |
| 3 | `tests/scenarios/03-no-progress.md` | No progress across iterations | `manual_validated` |
| 4 | `tests/scenarios/04-external-push.md` | External push detected | `manual_validated` |
| 5 | `tests/scenarios/05-draft-pr.md` | Draft PR | `design_only` |
| 6 | `tests/scenarios/06-scope-discipline.md` | Reviewer scope discipline | `manual_validated` |
| 7 | `tests/scenarios/07-pr-scope-under-threshold.md` | PR-scope check, under threshold | `ci_trusted` |
| 8 | `tests/scenarios/08-pr-scope-over-threshold.md` | PR-scope check, over threshold, splits recommended | `manual_validated` |
| 9 | `tests/scenarios/09-pr-scope-resume.md` | PR-scope check, resume after recorded decision | `ci_trusted` |
| 10 | `tests/scenarios/10-pr-scope-disabled.md` | PR-scope check disabled | `ci_trusted` |
| 11 | `tests/scenarios/11-count-new-loc-streams.md` | count_new_loc.sh stream separation | `ci_trusted` |
| 12 | `tests/scenarios/12-yagni-sibling-pr.md` | yagni reviewer sees sibling PR context | `design_only` |
| 13 | `tests/scenarios/13-adversary-catches-panel-miss.md` | Adversary catches panel miss | `design_only` |
| 14 | `tests/scenarios/14-test-intent-mismatch.md` | Move A test-intent mismatch | `design_only` |
| 15 | `tests/scenarios/15-second-instance-schema-permissive.md` | Move B second-instance sweep on permissive schema | `design_only` |
| 16 | `tests/scenarios/16-cross-doc-drift.md` | Move C cross-doc drift | `design_only` |
| 17 | `tests/scenarios/17-evidence-gated-solo-promotion.md` | Evidence-gated solo-adversary promotion | `ci_trusted` |
| 18 | `tests/scenarios/18-evidence-verification-fails.md` | Evidence verification failure path | `ci_trusted` |
| 19 | `tests/scenarios/19-panel-objection-suppresses-solo.md` | Panel objection suppresses solo-adversary promotion | `design_only` |
| 20 | `tests/scenarios/20-human-comments-feed.md` | Human-comments feed | `design_only` |
| 21 | `tests/scenarios/21-metrics-cross-record-invariant.md` | Metrics cross-record invariant | `ci_trusted` |
| 22 | `tests/scenarios/22-skill-split-anchors.md` | SKILL split docs anchors and drift guard | `ci_trusted` |
| 23 | `tests/scenarios/23-blind-spots-persona.md` | Blind-spots persona | `design_only` |
| 24 | `tests/scenarios/24-adversary-full-default.md` | full adversary context and required review completion | `manual_validated` |
| 25 | `tests/scenarios/25-persona-recall-sharpening.md` | Persona recall sharpening | `manual_validated` |
| 26 | `tests/scenarios/26-parallel-reviewer-fanout.md` | Parallel reviewer fan-out stays batched | `design_only` |
| 27 | `tests/scenarios/27-comment-reply-disposition.md` | Inline-comment disposition + reply + SUCCESS gate | `manual_validated` |
| 28 | `tests/scenarios/28-reviewer-working-tree.md` | Reviewers do not mutate the shared working tree | `design_only` |
| 29 | `tests/scenarios/29-yagni-responsibility.md` | YAGNI findings require evidence of unused or redundant responsibility | `manual_validated` |
| 30 | `tests/scenarios/30-tests-coverage-calibration.md` | Tests coverage findings name the behavior at risk | `manual_validated` |
| 31 | `tests/scenarios/31-required-small-fixes.md` | Required small fixes under higher-priority instructions | `design_only` |

Regenerate this table from `tests/scenarios/manifest.yaml` when adding a scenario; the manifest is the source of truth for both the row set and the tier.
