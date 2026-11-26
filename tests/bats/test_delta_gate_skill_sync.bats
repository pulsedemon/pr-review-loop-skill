#!/usr/bin/env bats

# Delta-gate cross-surface drift guard. Pins:
#   1. gate.schema.json `reviewer` enum == personas.yaml panel set
#      (the adversary is NOT gate-eligible and must be absent).
#   2. SKILL.md §4a.1 exists and links docs/delta-gate.md.
#   3. Both knobs (delta_gate, delta_gate_min_candidates) appear in SKILL.md.
#   4. docs/delta-gate.md exists and names the forced pre-approval sweep.

load test_helper

@test "gate.schema.json reviewer enum matches the personas.yaml panel" {
  local enum panel
  enum=$(python3 -c "import json;print(','.join(sorted(json.load(open('${REPO_ROOT}/reviewers/gate.schema.json'))['properties']['reviewer']['enum'])))")
  panel=$(python3 "${SCRIPTS}/personas_manifest.py" --list panel-names | LC_ALL=C sort | paste -sd, -)
  [ "$enum" = "$panel" ]
}

@test "gate.schema.json does not list the adversary" {
  run python3 -c "import json,sys;sys.exit(0 if 'adversary' not in json.load(open('${REPO_ROOT}/reviewers/gate.schema.json'))['properties']['reviewer']['enum'] else 1)"
  [ "$status" -eq 0 ]
}

@test "SKILL.md has a 4a.1 section that links docs/delta-gate.md" {
  grep -q '4a.1' "${REPO_ROOT}/SKILL.md"
  grep -q 'docs/delta-gate.md' "${REPO_ROOT}/SKILL.md"
}

@test "SKILL.md documents both delta-gate knobs" {
  grep -q 'delta_gate\b' "${REPO_ROOT}/SKILL.md"
  grep -q 'delta_gate_min_candidates' "${REPO_ROOT}/SKILL.md"
}

@test "docs/delta-gate.md exists and names the forced pre-approval sweep" {
  [ -f "${REPO_ROOT}/docs/delta-gate.md" ]
  grep -qi 'forced.*sweep\|pre-approval' "${REPO_ROOT}/docs/delta-gate.md"
}
