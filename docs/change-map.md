# Maintainer change map

> **Partly generator-backed.** Surfaces listed in `manifests/` are generated
> and validated by `scripts/regen-check.sh`; the rest are still pinned by the
> canary tests named in the rows below. See
> [`docs/generators.md`](generators.md) for the generator convention.

This is a **router, not a tutorial**. For each common edit it names the
source of truth, the dependent surfaces, and the command that validates the
change, then links to the canonical deep doc with the full procedure.

In this repo, edits to Markdown are behavior changes: `SKILL.md`,
`reviewers/*.md`, `docs/*.md`, and `templates/*.md` are read by a host LLM as
instructions (see `CLAUDE.md`). Before editing, find the source of truth
below: editing a derived surface directly is the most common mistake.

This table is the quick lookup; the section under it for each edit carries the
dependent surfaces and caveats. Edits not listed here are routed by the
"Pointers to authoritative docs" list in `CLAUDE.md`.

| Edit | Source of truth | Validate with |
| --- | --- | --- |
| [Add/remove/rename a persona](#addremoverename-a-persona) | `reviewers/personas.yaml` | `scripts/regen.sh` then `bash tests/run.sh` |
| [Change promotion logic / reasons](#change-promotion-logic--reasons) | `scripts/promote_findings.py` | `bash tests/run.sh` |
| [Edit the state schema](#edit-the-state-schema) | `templates/state.schema.json` | `bash tests/run.sh` |
| [Change adversary caps](#change-adversary-caps) | `manifests/adversary-caps.yaml` | `scripts/regen.sh` then `bash tests/run.sh` |
| [Skip another dev-only tree](#skip-another-dev-only-tree) | `manifests/dev-trees.yaml` | `scripts/regen.sh` then `bash tests/run.sh` |
| [Change a loop exit condition](#change-a-loop-exit-condition) | `scripts/check_exit_conditions.py` | `bash tests/run.sh` then `uv run python -m pytest -q` |
| [Change what the Step 5 summary shows](#change-what-the-step-5-summary-shows) | `docs/step5-summary.md` + `templates/summary_*.md` | `bash tests/run.sh` then `uv run python -m pytest -q` |
| [Add a CI integration](#add-a-ci-integration) | new `ci-integrations/<name>.md` | `bash tests/run.sh` |
| [Add or change host support](#add-or-change-host-support) | `install.sh` + `docs/model-overrides.md` | `bash tests/run.sh` + `bats tests/bats/install_uninstall.bats` |
| [Change reviewer/delta-gate fan-out orchestration contract](#change-reviewerdelta-gate-fan-out-orchestration-contract) | `SKILL.md` | `bash tests/run.sh` + Scenario 26 manual check |
| [Edit SKILL.md prose](#edit-skillmd-prose) | `SKILL.md` | `bash tests/run.sh` |
| [Add a generated surface](#add-a-generated-surface) | manifest + generator wiring | `scripts/regen.sh` then `bash tests/run.sh` |
| [Edit a procedure move / severity rule](#edit-a-procedure-move--severity-rule) | `docs/procedure-moves.md` or persona file | `bash tests/run.sh` |
| [Edit §3.5 PR-scope mechanics](#edit-35-pr-scope-mechanics) | `docs/pr-scope.md` | `bash tests/run.sh` |
| [Edit §4b reviewer orchestration](#edit-4b-reviewer-orchestration) | `docs/reviewer-orchestration.md` | `bash tests/run.sh` |
| [Edit scenario validation metadata](#edit-scenario-validation-metadata) | `tests/scenarios/manifest.yaml` | `python3 scripts/scenario_manifest.py --list tier-map` then `bats tests/bats/test_scenario_validation_sync.bats` |
| [Cite a repo path in markdown prose](#cite-a-repo-path-in-markdown-prose) | the citing `*.md` file | `python3 scripts/check_md_citations.py` (bats-wired) |

## Add/remove/rename a persona

- **Source of truth:** `reviewers/personas.yaml`
- **Dependent surfaces:** SKILL.md "Reviewer personas" list, the `reviewer`
  enum in `reviewers/output.schema.json`, the SKILL.md §4b Move A / A.1 /
  B / C bullets (from the `move_a`/`move_a1`/`move_b`/`move_c` flags), and
  panel-count phrases inside `<!-- regen:panel-count-* -->` regions
  across `SKILL.md`, `tests/scenarios/*.md`, and `reviewers/*.md`
  (all generator-managed via `scripts/regen.sh`); the `reviewers/<name>.md`
  file remains manual and is caught by a sync test, as is the agreement
  between each `move_*` flag and the `## Procedure move` headings on disk
  (`tests/bats/test_skill_moves_persona_sync.bats`)
- **Validate:** run `scripts/regen.sh`, then `bash tests/run.sh`;
  any remaining failures name the still-manual surfaces
- **See:** [`docs/editing-personas.md`](editing-personas.md)

## Add a shared reviewer addendum

- **Source of truth:** `reviewers/personas.yaml` `addendums:`
- **Dependent surfaces:** the `reviewers/_<name>_addendum.md` file itself, and
  the H2 link section in every persona that should honor it. Nothing is
  generator-managed here: no script concatenates the addendum, each reviewer
  follows the link from its own prompt, so both surfaces are manual
- **Validate:** `bash tests/run.sh`.
  `tests/bats/test_reviewer_enum_filesystem_sync.bats` pins the file against the
  manifest, `tests/bats/test_addendum_link_sync.bats` pins the per-persona links
- *Caveat:* the adversary is not in `panel:`, so a panel-driven loop misses it.
  Decide per addendum whether it applies (working-tree and output rules do, human-comments
  deliberately do not) and assert that choice in its own test.
- *Caveat:* `reviewers/*.md` is in the `--validate-coverage` corpus, so addendum
  prose must not carry unwrapped numbered persona-count phrases.
- **See:** [`docs/editing-personas.md`](editing-personas.md)

## Change promotion logic / reasons

- **Source of truth:** `scripts/promote_findings.py` (the only place a
  `suggestion` is promoted to `blocker`); the matcher rule lives in
  `scripts/match_findings.py` and canonically in `docs/synthesis.md`
- **Dependent surfaces:** `docs/synthesis.md`, `docs/adversary.md`, and
  `reviewers/adversary.md`; public inputs in `SKILL.md` and fresh-run defaults in
  `scripts/pr_loop_state.py`. Preserve historical metric fallbacks when changing defaults.
- **Validate:** `bash tests/run.sh`
- *Caveat:* if you are editing only the reason *enum strings* in reviewer
  JSON, the source of truth is `reviewers/output.schema.json` instead.
- **Evaluation:** [Evaluating reviewer changes](editing-personas.md#evaluating-reviewer-changes).
- **See:** [`docs/synthesis.md`](synthesis.md)

## Edit the state schema

- **Source of truth:** `templates/state.schema.json`
- **Dependent surfaces:** `scripts/` state helpers that read/write the
  changed fields; the resume state machine described in `docs/resume.md`
- **Validate:** `bash tests/run.sh` (state, metric, and resume tests)
- *Caveat:* state is ephemeral and off-tree at `<git-dir>/pr-loop/state.json`;
  the schema is the canonical shape.
- **See:** [`docs/resume.md`](resume.md)

## Change a loop exit condition

- **Source of truth:** `scripts/check_exit_conditions.py` for the `NO_PROGRESS`
  and `CI_STUCK` comparisons, and `scripts/finding_matcher.py` for how two
  blockers are matched. `SKILL.md` §4d and §4d.1 name the script and link to
  `docs/exit-conditions.md`; they do not restate the rules.
- **Dependent surfaces:** `docs/exit-conditions.md` (mechanics),
  `docs/ci-conversion.md` (the `ci_wait.sh` exit-code mapping feeding
  `CI_STUCK`). Changing how blockers are matched affects §4c dedupe too, so
  check `docs/synthesis.md` before touching `is_match`. Its scorer, threshold,
  and line window are keyword-only arguments defaulting to the §4c values;
  changing a *default* changes loop behavior, while the recall harness passes
  its own and does not.
- **Do not restate the matcher threshold in `SKILL.md`.** `tests/run.sh` exits 3
  if it appears there; link to `docs/synthesis.md` instead.
- **Validate:** `bash tests/run.sh` for
  `tests/bats/test_check_exit_conditions.bats`, which covers the decisions, then
  `uv run python -m pytest -q` for
  `scripts/tests/test_finding_matcher_fallback.py`. `tests/run.sh` ends by
  exec'ing bats and never collects pytest; CI runs them as separate jobs.

## Change what the Step 5 summary shows

- **Source of truth:** `templates/summary_ready.md` and
  `templates/summary_needs_attention.md` for the sections, `docs/step5-summary.md`
  for what fills each one. `SKILL.md` Step 5 carries the contract (which template,
  the marker, the attribution rule) and links out for the rest.
- **A partition with no section is invisible.** `promote_findings.py` partitions
  every finding and `pr_loop_state.py` counts it, so a severity that no template
  renders is counted and then dropped; that was the nit tier before #115 and
  in-scope suggestions before #116. Adding a severity means adding a section.
- **Suggestion and nit bullets come from `scripts/collect_open_findings.py`,**
  not from the last iteration's partitions: a delta-gated iteration skips
  personas, so an earlier finding whose owner did not run again is still open.
  The resolution rule lives in
  `docs/step5-summary.md#carrying-open-suggestions-and-nits`; matching is
  `scripts/finding_matcher.py`, shared with §4c. Do not restate either in
  `SKILL.md`.
- **Dependent surfaces:** `docs/synthesis.md` (which partition a severity lands
  in), `templates/state.schema.json` (`promotion_reason`, whose values the
  provenance suffix keys on, and the `addressed[]` `fixed_from` record
  `collect_open_findings.py` settles on).
- **Validate:** `bash tests/run.sh` for
  `tests/bats/test_open_findings_contract.bats`,
  `tests/bats/test_nit_tier_contract.bats` and
  `tests/bats/test_step5_summary_contract.bats`, then `uv run python -m pytest -q`
  for `scripts/tests/test_collect_open_findings.py`.

## Skip another dev-only tree

- **Source of truth:** `manifests/dev-trees.yaml`, the `dev_trees:` list,
  propagated by `scripts/regen_dev_trees.py` to four surfaces, each in its
  own syntax: `CURSOR_INSTALL_SKIP_NAMES` in `install.sh`,
  `CAP_GREP_EXCLUDES` in `tests/run.sh`, `copy_skill_tree`'s rsync excludes
  in `tests/bats/test_helper.bash`, and the leading `_GREP_EXCLUDES` entries
  in `scripts/regen_move_a1_enum.py`.
- **Dependent surfaces:** never edit the generated blocks directly. These
  four lists drifted five ways by hand, which is how `.worktrees` ended up
  shipping into the Cursor install.
- **Not for content-specific excludes.** `docs/superpowers` and
  `tools/recall-harness/*` mean different things to each consumer
  (not-installable vs not-cap-scannable vs not-enum-scannable) and stay
  local to the consumer that needs them.
- **Validate:** `scripts/regen-check.sh` (CI gate; exits 5 on drift) plus
  `bash tests/run.sh`.

## Change adversary caps

- **Source of truth:** `manifests/adversary-caps.yaml`, the single `cap:`
  value, propagated by `scripts/regen_adversary_caps.py` to all three
  mirrors (both schema maxima in `templates/state.schema.json`, the
  preset-guard + `readonly` in `scripts/_adversary_caps.sh`, and the cap
  sentence inside the `<!-- regen:adversary-caps:start/end -->` region
  in `docs/adversary.md`).
- **Dependent surfaces:** never edit the mirrors directly; edit `cap` in
  `manifests/adversary-caps.yaml`, then run `scripts/regen.sh` to
  propagate. The next `scripts/regen.sh` run will revert any direct edit
  to a mirror back to the manifest value.
- **Validate:** `scripts/regen-check.sh` (CI gate; exits non-zero on
  drift) plus `bash tests/run.sh` (which also runs `state_init.sh`'s
  runtime cross-check of `ADVERSARY_CAP` against both schema maxima, and
  the prose-home drift guard).
- *Caveat:* Markdown surfaces (`SKILL.md`, `CLAUDE.md`) say "the cap",
  never the literal; only the manifest and the three mirror surfaces
  above carry the value.
- **See:** [`docs/adversary.md`](adversary.md), [`docs/generators.md`](generators.md)

## Add a CI integration

- **Source of truth:** a new `ci-integrations/<name>.md` file
- **Dependent surfaces:** the "Existing integrations" table in
  `ci-integrations/README.md` must gain a row; optional fetch scripts under
  `scripts/`
- **Validate:** `bash tests/run.sh`
- *Caveat:* CI failures are always in-scope blockers; the integration's
  blocker mapping must satisfy `history.findings[]` in
  `templates/state.schema.json`, not `reviewers/output.schema.json`.
- **See:** [`docs/ci-conversion.md`](ci-conversion.md)

## Add or change host support

- **Source of truth:** `install.sh` (detection predicates, target paths) and
  the `### <host>` section of `docs/model-overrides.md` (tier mapping)
- **Dependent surfaces:** the "Works with" line, install table, and per-host
  setup sections in `README.md`; the shipped-artifact paragraph in `CLAUDE.md`;
  opencode's tier agent files under `hosts/opencode/agent/`; the install-smoke
  job in `.github/workflows/ci.yml`; the auto-update sections in
  [`docs/skill-update.md`](skill-update.md)
- **Validate:** `bash tests/run.sh`, then install into a clean fake HOME and
  reload the host once (opencode needs a restart; config has no hot reload)
- *Caveat:* opencode's `task` tool has no per-invocation model parameter, so
  tiers there resolve to installed agent definitions via `subagent_type`.
  opencode is the only host where routing is necessarily config-time rather
  than spawn-time. A
  host flag must keep forcing its host past detection, and `--force` alone must
  keep installing every host regardless of detection.
- **See:** [`docs/model-overrides.md`](model-overrides.md)

## Change reviewer/delta-gate fan-out orchestration contract

- **Source of truth:** `SKILL.md` (§4a.1 and §4b)
- **Dependent surfaces:** `AGENTS.md`, `README.md`, and `docs/delta-gate.md`
  must mirror the same batching/fallback/output-isolation contract; the
  deterministic guard lives in `tests/bats/test_parallel_fanout_contract.bats`
  and the host-timeline regression check lives in
  `tests/scenarios/26-parallel-reviewer-fanout.md`
- **Validate:** `bash tests/run.sh`, then manually run Scenario 26 on a host
  that supports parallel subagent spawning whenever orchestration wording
  changes
- *Caveat:* repo tests can pin the contract text and cross-surface drift, but
  only the manual scenario can prove the host actually batched the launches.
- **See:** [`docs/delta-gate.md`](delta-gate.md),
  [`tests/scenarios/26-parallel-reviewer-fanout.md`](../tests/scenarios/26-parallel-reviewer-fanout.md)

## Edit SKILL.md prose

- **Source of truth:** `SKILL.md`
- **Dependent surfaces:** none generated, but two guardrails apply: the
  bats-pinned line cap (`test_skill_md_length.bats`) and the `tests/run.sh`
  matcher-rule drift guard
- **Validate:** `bash tests/run.sh`
- *Caveat:* `SKILL.md` is line-capped to force the "helper scripts over
  inlined logic" discipline, and the `token_overlap >= 0.6` matcher line must
  never appear in it; keep that rule in `docs/synthesis.md` only.
- **See:** [`CLAUDE.md`](../CLAUDE.md), "Editing rules specific to this repo"

## Add a generated surface

- **Source of truth:** the manifest (`reviewers/personas.yaml`) plus the
  generator wiring: `scripts/cogfiles.txt` for a cog region, or a new
  standalone script for comment-less formats
- **Dependent surfaces:** the new markered region or script; a canary bats
  test pinning the marker/region presence
- **Validate:** run `scripts/regen.sh`, then `bash tests/run.sh`
- *Caveat:* every generator must honor the two-mode (`--check`/`--write`)
  contract and exit-code convention; CI runs `scripts/regen-check.sh`.
- **See:** [`docs/generators.md`](generators.md)

## Edit a procedure move / severity rule

- **Source of truth:** `docs/procedure-moves.md` for Move C (its wording is
  identical across personas); the persona's own `reviewers/*.md` file for
  Move A / A.1 / B (wording is tuned per domain)
- **Dependent surfaces:** the SKILL.md §4b paraphrase of the Move C rule;
  `move_c: true` personas that link to `docs/procedure-moves.md`
- **Validate:** `bash tests/run.sh` (the Move C and Move A.1 drift guards)
- **Evaluation:** [Evaluating reviewer changes](editing-personas.md#evaluating-reviewer-changes).
- *Caveat:* on a persona that has both an applicability gate and procedure
  moves, the gate must name the **independently triggered** moves it does not
  override, or the prompt instructs both `approve` and a blocker on the same
  diff. `requirements` does this for Move C, and `blind_spots` for Move A and
  Move C; both are pinned by `tests/bats/test_applicability_gate_text.bats`.
  Move B needs no conjunct: it fires only after a finding exists, so it cannot
  reach the early-exit path.
- *Caveat:* on a persona whose applicability gate early-exits above the
  severity sections (`yagni`, `blind_spots`), a severity rule must cite the
  gate surface id(s) that admit it, e.g. `- (c) ...`, or `- (b)(c)(d) ...` for a
  rule that spans surfaces. A rule naming a surface the gate does not list is
  unreachable: the persona exits above it. Pinned by
  `tests/bats/test_gate_rule_reachability.bats`.
- **See:** [`docs/procedure-moves.md`](procedure-moves.md),
  [`docs/editing-personas.md`](editing-personas.md)

## Edit scenario validation metadata

- **Source of truth:** `tests/scenarios/manifest.yaml`
- **Dependent surfaces:** the `## Validation status` section in each
  `tests/scenarios/*.md` file; the tier explanation in `tests/README.md`
- **Validate:** `python3 scripts/scenario_manifest.py --list tier-map`, then
  `bats tests/bats/test_scenario_validation_sync.bats`
- *Caveat:* `ci_trusted` scenarios must cite proof-source path(s) exactly as
  written in the manifest; `manual_validated` scenarios must point to the
  recorded passing run in the file; `design_only` scenarios must explain what
  evidence would promote them.
- **See:** [`tests/README.md`](../tests/README.md),
  [`tests/scenarios/manifest.yaml`](../tests/scenarios/manifest.yaml)

## Edit §3.5 PR-scope mechanics

- **Source of truth:** `docs/pr-scope.md` (the four substeps, the three
  agent verdicts, the resume-skip rules, and both non-interactive defaults)
- **Dependent surfaces:** the §3.5 summary in `SKILL.md` (one paragraph
  pointing here); `gates/pr-scope.md` (the agent prompt itself);
  `scripts/pr_scope_step.py` (state and sidecar persistence)
- **Validate:** `bash tests/run.sh`. `test_pr_scope_doc_canaries.bats`
  pins the five `user_decision` values, the three verdicts, and both
  non-interactive defaults
- *Caveat:* the user-visible automation contract (when prompts are
  allowed; abort path → `SCOPE_SPLIT_RECOMMENDED`) stays in `SKILL.md`.
  Anything procedural (substeps, verdict-branch table, persistence
  order) is here.
- **See:** [`docs/pr-scope.md`](pr-scope.md)

## Edit §4b reviewer orchestration

- **Source of truth:** `docs/reviewer-orchestration.md` (reviewer-output
  handling rules including the load-bearing "never pre-create an empty
  file" prose, the procedure-expectation contract that drives
  shallow-review detection, and the reviewer budget with its per-host
  recipes)
- **Dependent surfaces:** the §4b summary in `SKILL.md` (one paragraph
  pointing here, keeping the "never pre-create an empty file" phrase
  verbatim, plus the one-sentence reviewer-budget pointer);
  `reviewers/output.schema.json` (the `evidence` object shape);
  `scripts/flag_shallow_reviews.py` (the enforcer)
- **Validate:** `bash tests/run.sh`. `test_reviewer_orchestration_doc_canaries.bats`
  pins three full-phrase canaries: "Reviewer JSON is transient", "never
  pre-create an empty file", and "verdict: approve with missing or
  empty evidence.files_read". `test_reviewer_runtime_bound.bats` pins the
  reviewer budget, and `test_parallel_fanout_contract.bats` pins its §4b
  pointer
- *Caveat:* the schema is the canonical contract for reviewer output
  shape; this doc owns the orchestrator's behavior, not the JSON shape.
- **See:** [`docs/reviewer-orchestration.md`](reviewer-orchestration.md)

## Cite a repo path in markdown prose

- **Source of truth:** the citing `*.md` file
- **Dependent surfaces:** none
- **Validate:** `python3 scripts/check_md_citations.py` (wired into the bats
  suite via `tests/bats/test_md_citations.bats`, so `bash tests/run.sh` and CI
  both run it)
- *Caveat:* backticked path citations must resolve from the repo root against
  git-tracked files; file-relative citations are rejected even when they
  resolve from the citing file's directory, because quoted prose moves between
  files. Markdown *link* targets are the opposite: file-relative, since that
  is how GitHub resolves them. `tests/scenarios/` (fictional fixture paths)
  and `docs/superpowers/` (frozen specs) are excluded; generated artifacts the
  docs legitimately cite (`tools/recall-harness/REPORT.md`) are allowlisted in
  the script.

---

For any edit not listed above, see the "Pointers to authoritative docs"
section of [`CLAUDE.md`](../CLAUDE.md).
