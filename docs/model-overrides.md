# Subagent model overrides

This document owns portable subagent model routing for the PR Review Loop. `SKILL.md` exposes the inputs; hosts apply this file when spawning the `delta_gate`, `reviewer`, `adversary`, and `pr_scope` phases.

## Inputs and precedence

- `subagent_model_profile` defaults to `balanced`. Allowed values: `balanced`, `inherit`, `cost_saver`.
- `subagent_model_overrides` is an optional map keyed by phase: `delta_gate`, `reviewer`, `adversary`, `pr_scope`. Allowed values for each phase: `inherit`, `cheap`, `standard`, `strong`.

Malformed or unknown routing input must degrade to inherited routing and must never block the loop. Treat unknown `subagent_model_profile` values as `inherit`; unknown phase keys in `subagent_model_overrides` are ignored; and unknown tier values are treated as `inherit` for that phase.

Precedence is:

1. Explicit `subagent_model_overrides.<phase>` wins.
2. Otherwise the `subagent_model_profile` baseline applies:
   - `balanced` (default) maps `delta_gate` and `pr_scope` to `cheap`, `reviewer` to `standard`, and `adversary` to `strong`. The panel reviews on a cost-efficient tier while the adversary keeps the strongest available model.
   - `cost_saver` maps `delta_gate`, `pr_scope`, and `reviewer` to `cheap` and `adversary` to `standard`: cheaper everywhere, with the adversary still one tier above the panel.
   - `inherit` maps every phase to `inherit`.
3. A phase with no explicit override and no profile mapping uses `inherit`.

`inherit` means omit any per-subagent model override and let the host use the same model as the parent orchestration session.

## Portable tiers

The portable tier names are intent labels, not raw model IDs:

| Tier | Intended use |
| --- | --- |
| `inherit` | Use the parent session model. Selected by the `inherit` profile, an explicit per-phase override, or when no profile maps the phase. |
| `cheap` | Cost-efficient relevance or routing work. Default for the delta-gate and PR-scope phases under the `balanced` profile. |
| `standard` | General-purpose coding/review work. Default for the reviewer panel under the `balanced` profile. |
| `strong` | Highest-quality model available in the host for complex review judgment. Default for the adversary under the `balanced` profile. |

Unsupported hosts or unsupported tier mappings must silently fall back to the inherited model and continue the loop. Model routing is an optimization; it must never block review, synthesis, CI handling, or final summary posting.

## Observability and recording

The resolved tier→model decision happens in the host at spawn time, so the host is the only reliable source of what each subagent actually ran on. Surface it locally, never in the posted PR comment (the Step 5 summary stays neutral and attribution-free; see [`step5-summary.md`](step5-summary.md)).

- **Live echo.** As each fan-out phase is spawned (`delta_gate` relevance subagents in §4a.1, the `reviewer` panel in §4b, the `adversary` in §4d.0), echo its resolved routing to the session: `<phase> → <tier> (<model>)`, e.g. `reviewer → standard (sonnet)`. When a phase resolves to `inherit`, print `<phase> → inherit (parent model)`. This is the live "which model is each subagent using" display.
- **State recording.** After resolving and spawning, record each phase that ran into `history[N].model_routing.<phase>` as `{ "tier": <portable tier>, "model": <concrete host model> }` (shape canonical in [`templates/state.schema.json`](../templates/state.schema.json) `$defs/phase_model`). Omit `model` when the tier is `inherit` and the host did not name the parent-session model. Only `delta_gate`, `reviewer`, and `adversary` are recorded; the once-per-loop `pr_scope` phase is not. Recording is best-effort: on any failure, skip the field and continue.
- **Metric rollup.** `scripts/write_iteration_metric.sh` (via `build_iteration_metric`) folds `model_routing` into a `models` map (phase → concrete model, falling back to the tier label when no model was recorded) on each per-iteration metric line under `<git-dir>/pr-loop/metrics.jsonl`.
- **Step 5 terminal output.** The end-of-loop terminal (stdout) output may print a per-iteration model-routing recap from `history[].model_routing`; the posted PR comment never includes it.

## Host behavior

### Claude Code

Prefer a per-invocation model override when available. Otherwise use generated or declared subagent configuration with a `model` field. Respect Claude Code's own override precedence, including `CLAUDE_CODE_SUBAGENT_MODEL`.

Map portable tiers to Claude aliases, not dated model IDs:

| Tier | Claude alias |
| --- | --- |
| `cheap` | `haiku` |
| `standard` | `sonnet` |
| `strong` | `opus` |

### Codex

Codex's `spawn_agent` uses the parent model when no `model` is passed. Pass `model` for phases whose resolved tier is not `inherit`, and omit it for phases that resolve to `inherit`.

Map portable tiers to Codex model families, not dated model IDs, and pass the newest model of that family that the active `spawn_agent` tool metadata lists. The families follow the metadata's own descriptions: `luna` is fast and affordable for easier tasks, `sol` is for coding and everyday work, and `astra` is for complex coding and professional work.

| Tier | Codex family | Listed on 2026-11-22 |
| --- | --- | --- |
| `cheap` | `luna` | `gpt-6-luna` |
| `standard` | `sol` | `gpt-6.1-sol` |
| `strong` | `astra` | `gpt-6-astra` |

If the active Codex tool metadata changes or a listed model is unavailable, use another supported model that clearly fits the same portable tier. Otherwise fall back to `inherit`: omit `spawn_agent.model` and continue the loop.

### opencode

opencode's `task` tool dispatches by `subagent_type` (an agent name) and takes
no per-invocation model parameter, so tiers resolve to pre-declared subagent
definitions that `install.sh --opencode` links into the opencode agent dir:

| Tier | `subagent_type` |
| --- | --- |
| `cheap` | `prl-cheap` |
| `standard` | `prl-standard` |
| `strong` | `prl-strong` |
| `inherit` | `general` (built-in) |

The tier agents ship from `hosts/opencode/agent/` with no `model` field. A
model-less agent inherits the orchestration session's model (the `task` tool
falls back to the parent message's model and variant), so every tier initially
behaves exactly like `inherit`. opencode therefore honors true `inherit`:
`general` and any model-less agent run on the parent session model, and the
inherit echo is `<phase> → inherit (parent model)` like every other host. Set
`model: <provider>/<model-id>` in each installed agent file to activate tiered
routing, then restart opencode: it reads config, skills, and agents once at
startup, with no hot reload. The installed files are symlinks into the skill
checkout, so a `model:` edit leaves that clone dirty and
[`skill-update.md`](skill-update.md) startup-sync stops fast-forwarding it
until the edit is committed or reverted.

The agents carry no `permission` block: opencode subagents inherit the session
permission ruleset, same as panel reviewers on every other host, and the
working-tree guardrails stay prompt-enforced
([`reviewers/_working_tree_addendum.md`](../reviewers/_working_tree_addendum.md)).
A per-agent `edit: deny` was considered and rejected: the documented
tree-mutation failures came through bash, which such a block leaves open, so it
would guard a class the addendum does not need help with while looking like
enforcement.

Two opencode-specific handling points:

- Tiers are configured at install time, not per call. Echo tiers with the
  agent name in place of a concrete model: `reviewer → standard
  (prl-standard)`; once an agent file names a `model:`, print that model
  instead.
- When the resolved agent is not registered (skill installed without the
  agents, user deleted them), fall back to `general` and continue. Model
  routing must never block the loop.

Record `history[].model_routing.<phase>.tier` as usual but leave `model` unset
unless the agent file names one; for phases with no recorded model the
per-iteration metric rollup then shows the tier label.

### Cursor Agent

Use the closest supported per-subagent or task model override when the active Cursor agent runtime exposes one. If Cursor only exposes top-level `--model`, the whole session model remains the effective model and phase-specific overrides are advisory instructions.

Do not require Cursor-only files, APIs, or generated configuration unless those surfaces are verified in the active Cursor runtime.

### Witch

Under Witch, every phase delegates through Witch's familiar wrappers after `--route`, following the delegation instructions Witch gives the session ([Witch rules](https://github.com/pulsedemon/witch/blob/main/docs/rules.md#witch-commands-and-compaction)), and this section replaces the Claude Code and Codex sections' spawn and tier mappings.

| Phase | Work kind |
| --- | --- |
| `delta_gate` | `investigation` |
| `reviewer` | `review` |
| `adversary` | `investigation` |
| `pr_scope` | `investigation` |

`review` returns a route per installed runtime by default and `investigation` one; `investigation` starts on the parent's runtime unless Witch's capacity balancing moves it. A panel route passes `--of <producer runtime>:<producer model>` when the parent knows what produced the diff under review. Route once per batch: the delta-gate pre-pass, each panel batch, the adversary and the scope gate. A forced full sweep is its own batch, and its routing replaces the partial pass's in `model_routing.reviewer`, as its receipts do. A batch with no selected persona is not routed, launches nothing and records no routing.

A tiered phase routes with `--tier <tier>`, which replaces the inherit fallback above; Witch maps the tier to each runtime's model, and a pinned `/delegation` rule keeps its own model. An `inherit` phase routes with `--named <parent runtime>:<parent model>`, which returns one route; it is never routed twice for coverage and moves off the parent's model only by the usage reroute below. A refused route goes to the user with Witch's reason, is not retried without the tier, and takes the phase's failure record, with no prompt.

The tier's level is passed as `-c model_reasoning_effort="<level>"` on Codex and `--effort <level>` on Claude:

| Tier | Codex | Claude |
| --- | --- | --- |
| `cheap` | `low` | `low` |
| `standard` | `medium` | `medium` |
| `strong` | `high` | `high` |

`inherit` passes no effort flag and runs at its runtime's configured default effort, which can be `max` on Codex.

Launch every reviewer, gate and adversary familiar lean: Codex with Witch's `--without-mcp`, Claude with `--strict-mcp-config` and `--disable-slash-commands` (pulsedemon/witch#919 tracks Witch documenting this).

With `N >= 1` selected personas and `R` the number of entries in the result's `routes`, in returned order, launch `max(N, R)` familiars: familiar `k` runs persona `k mod N` on route `k mod R`. `folded` placements already run on an existing route and get no familiar. Every route gets a familiar and every persona runs at least once. The panel's [reviewer budget](reviewer-orchestration.md#reviewer-budget) applies per familiar.

Read each familiar's response with [`scripts/familiar_response.py`](../scripts/familiar_response.py) `<report-file>` and pipe it into the phase's validator. It returns the last JSON object that starts a line and ends the report, apart from Witch's own trailing lines. Leading text is this host's one loosening of the strict-JSON rule, needed because Codex reports carry the familiar's progress messages. A fenced object is malformed, as on every host. Never edit the object.

Each response is judged on its own, then several results for one persona combine per phase:

- Panel: every valid panel output goes to synthesis under its persona name, and the persona gets one receipt if any output validates. Every familiar that ends without a valid output, after any resend, records its own `reviewer_errors` entry, even beside another route's valid output. Same-name outputs count once toward multi-source promotion.
- Delta gate: a persona with any failed or invalid gate familiar gets no gate result, so it fails open; otherwise it gets one result, `relevant: true` if any familiar says so.
- Adversary: a missing or invalid response records `adversary_error` naming each failure. Otherwise a response that fails [the adversary's checks](adversary.md#failure-handling) is recorded as `history[].adversary`, first in route order, and takes that exit; otherwise the first valid response in route order is recorded. Every valid response goes to `scripts/flag_shallow_reviews.py` and its findings through the adversary merge in `scripts/promote_findings.py` into `history[].findings`; with a failure recorded, they reach §4e on the forced path and are only recorded on the approval path.
- Scope gate: present every valid recommendation in full; persist the first valid `request_split` in route order, else the first valid `atomic`. Scope errors are recorded beside a valid recommendation with `finalize --agent-error`, and a scope gate with no valid output takes the failed-agent row of [`pr-scope.md`](pr-scope.md#substeps).

A familiar cannot be messaged, so a resend for malformed panel output relaunches that persona with the validator's error appended, inside the same budget, on the same runtime and model: route with the phase's work kind and `--named <that runtime>:<that model>`, which returns that one route; a valid relaunch recovers the assignment and records no error. Gates fail open and the adversary records its error, as on other hosts.

A familiar refused for its usage limit is relaunched once per phase per iteration: route again with the phase's work kind and tier (`inherit` drops `--named`), keep only returned routes on another runtime, and apply `max(N, R)` over them with `N` the refused personas. A relaunch that validates recovers the assignment, adds its model to the recorded list and is named in the terminal output; for `inherit` the echo says the tier was not honoured. A second refusal, or no route on another runtime, takes the phase's failure record. Any other failed launch is that familiar's failure under the rules above.

Echo a phase as `<phase> → <tier> (<model>, <model>)`, and record `model_routing.<phase>.model` as the route models joined by `, ` in route order.
