#!/usr/bin/env bats

# The Step 5 open-sets contract (issue #116).
#
# Two halves have to hold together, and each fails silently on its own:
#
#   1. Both summary templates carry a Suggestions section. `partition()` routes
#      an in-scope, unpromoted suggestion to `suggestions[]` and
#      `pr_loop_state.py` counts it in `n_suggestions`; with no section it is
#      counted and then never shown — the same gap the nit tier hit in #115.
#   2. Step 5 fills those bullets from `scripts/collect_open_findings.py`, not
#      from the last iteration's partitions. A delta-gated iteration runs a
#      subset of the panel, so an earlier suggestion or nit whose owner was
#      skipped is persisted in history[] and never revisited.
#
# Mutation checks these would catch:
#   - drop the Suggestions block from either template -> that template's case
#   - drop the script from SKILL.md Step 5 -> the wiring case (the doc alone
#     does not make the host run it)
#   - render only the last iteration's partitions -> the behavioral case

load test_helper

collect() {
  echo "$1" | python3 "${SCRIPTS}/collect_open_findings.py" --state "$2"
}

nit() { # reviewer summary -> one persisted nit
  jq -nc --arg r "$1" --arg s "$2" \
    '{reviewer:$r, severity:"nit", scope:"in_scope", file:"src/a.py", line:10, summary:$s}'
}

setup() {
  STATE="${BATS_TEST_TMPDIR}/state.json"
  SUMMARY="retry budget is not reset between attempts"
}

@test "both summary templates render a suggestions section" {
  local tpl
  for tpl in summary_ready.md summary_needs_attention.md; do
    grep -qi '^\*\*Suggestions' "${REPO_ROOT}/templates/${tpl}" || {
      echo "templates/${tpl} has no suggestions block"
      echo "  — an in-scope suggestion is partitioned into suggestions[] and"
      echo "    counted in n_suggestions, then silently dropped from the summary"
      return 1
    }
  done
}

@test "SKILL.md Step 5 wires the open-sets script" {
  grep -q 'scripts/collect_open_findings.py' "${REPO_ROOT}/SKILL.md" || {
    echo "SKILL.md never names scripts/collect_open_findings.py"
    echo "  — docs/step5-summary.md holds the mechanics, but the host reads"
    echo "    SKILL.md for what to run"
    return 1
  }
}

@test "docs/step5-summary.md owns the resolution rule" {
  local doc="${REPO_ROOT}/docs/step5-summary.md"
  grep -q '^## Carrying open suggestions and nits' "$doc" || {
    echo "docs/step5-summary.md lost the open-sets section heading"
    echo "  — SKILL.md links to its anchor"
    return 1
  }
  # The five rows are the rule. Each is a distinct decision; losing one turns
  # the table into prose that no longer says what settles a finding. The last
  # four phrases are the contract a host has to get right to call the script
  # at all: that the adversary is not a panel persona, who owns a finding, that
  # ownership accumulates rather than tracking the newest sighting, and that a
  # pre-iteration status is not an error.
  local phrase
  for phrase in \
    'Re-raised it (matched per' \
    'Re-raised it as a blocker, promoted it, or deferred it' \
    'holds its `fixed_from` record' \
    'Ran its owning persona and did not re-raise it' \
    'Skipped its owning persona' \
    'The adversary is not a panel persona' \
    'owning personas are its `source_reviewers`' \
    'Owners **accumulate across sightings**' \
    '`iteration: 0` is legal'; do
    grep -qF "$phrase" "$doc" || {
      echo "docs/step5-summary.md lost a resolution-rule row: ${phrase}"
      return 1
    }
  done
}

@test "the resolution rule is not restated in SKILL.md" {
  # Same discipline as the matcher rule: SKILL.md paraphrases and links, so the
  # two cannot drift. first_seen_iteration is the rule's field, not a knob.
  ! grep -q 'first_seen_iteration' "${REPO_ROOT}/SKILL.md" || {
    echo "SKILL.md restates the open-sets rule; keep it in docs/step5-summary.md"
    return 1
  }
}

@test "a nit whose owner the delta gate skipped survives to Step 5" {
  local n
  n=$(nit "tests" "$SUMMARY")
  jq -nc --argjson n "$n" \
    '{schema_version:1, iteration:1, history:[
       {iteration:1, findings:[$n],
        panel_selection:{mode:"delta_gated", ran:["tests"], skipped:[],
                         gate_relevant:[], gate_fail_open:[],
                         open_blocker_carryover:[]}}]}' >"$STATE"

  run collect '{"iteration":2,"suggestions":[],"nits":[],"panel_ran":["correctness"]}' "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r '.nits | length' <<<"$output")" -eq 1 ]]
  [[ "$(jq -r '.nits[0].summary' <<<"$output")" == "$SUMMARY" ]]
  [[ "$(jq -r '.carried' <<<"$output")" -eq 1 ]]
  # Attribution never reaches the renderer.
  [[ "$(jq -r '.nits[0] | has("reviewer")' <<<"$output")" == "false" ]]
}

@test "the same nit is dropped once its owner runs again without it" {
  local n
  n=$(nit "tests" "$SUMMARY")
  jq -nc --argjson n "$n" \
    '{schema_version:1, iteration:1, history:[
       {iteration:1, findings:[$n],
        panel_selection:{mode:"delta_gated", ran:["tests"], skipped:[],
                         gate_relevant:[], gate_fail_open:[],
                         open_blocker_carryover:[]}}]}' >"$STATE"

  run collect '{"iteration":2,"suggestions":[],"nits":[],"panel_ran":["tests"]}' "$STATE"
  [[ "$status" -eq 0 ]]
  [[ "$(jq -r '.nits | length' <<<"$output")" -eq 0 ]]
}

@test "the state schema declares source_reviewers on persisted findings" {
  # The owner set is what decides whether a finding can be settled, and §4c
  # unions it across personas. A schema that declares only the singular
  # `reviewer` makes a co-owned finding look like one persona's the moment it
  # is persisted, and either owner alone then retires it.
  local declared
  declared=$(jq -r '.properties.history.items.properties.findings.items.properties
                    | has("source_reviewers")' "${REPO_ROOT}/templates/state.schema.json")
  [[ "$declared" == "true" ]] || {
    echo "templates/state.schema.json does not declare source_reviewers on history[].findings[]"
    return 1
  }
}
