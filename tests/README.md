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

For the current scenario list and each scenario’s tier, use the tier-map command under
[Scenario validation tiers](#scenario-validation-tiers).
