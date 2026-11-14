#!/usr/bin/env bats

# Generator-check canary for the README "Loop statuses" table.
#
# scripts/regen-check.sh invokes cog over every file in
# scripts/cogfiles.txt. If a future refactor strips the cog markers
# from README.md or removes README.md from cogfiles.txt, cog --check
# would silently pass with nothing to check for that file. Pin both
# (markers + cogfiles routing) so that case fails loudly.
#
# This file is the README's analogue of
# tests/bats/test_persona_surfaces_generator_check.bats (which guards
# the same invariant for SKILL.md).
#
# Mutation-tested before requesting review:
#   - delete the cog open marker from README.md → "missing cog open
#     marker" failure.
#   - drop "README.md" from scripts/cogfiles.txt → "missing README.md
#     entry" failure.
#   - corrupt templates/exit_statuses.yaml (add a key not in the schema
#     enum) → regen-check.sh exits non-zero with the
#     ExitStatusManifestError diagnostic.

load test_helper

@test "cog markers are present in README.md (canary against silent marker removal)" {
  grep -qF "<!--[[[cog" "${REPO_ROOT}/README.md" || {
    echo "README.md missing cog open marker '<!--[[[cog'"
    echo "Did a refactor strip the generator region around the 'Loop statuses' table?"
    return 1
  }
  grep -qF "<!--[[[end]]]-->" "${REPO_ROOT}/README.md" || {
    echo "README.md missing cog end marker '<!--[[[end]]]-->'"
    return 1
  }
}

@test "scripts/cogfiles.txt routes cog at README.md (canary against silent re-routing)" {
  grep -E '^[[:space:]]*README\.md[[:space:]]*$' "${REPO_ROOT}/scripts/cogfiles.txt" >/dev/null || {
    echo "scripts/cogfiles.txt is missing a 'README.md' entry."
    echo "Without it, scripts/regen-check.sh would silently pass while README.md drifts."
    echo "Current contents:"
    cat "${REPO_ROOT}/scripts/cogfiles.txt"
    return 1
  }
}

@test "templates/exit_statuses.yaml exists and parses" {
  local f="${REPO_ROOT}/templates/exit_statuses.yaml"
  [[ -f "$f" ]] || {
    echo "templates/exit_statuses.yaml missing — the cog snippet in README.md cannot render"
    return 1
  }
  python3 -c "
import sys, yaml
data = yaml.safe_load(open('$f').read())
assert isinstance(data, dict) and isinstance(data.get('statuses'), dict), \
    'top-level must be a mapping with a non-empty statuses mapping'
assert data['statuses'], 'statuses mapping must be non-empty'
" || return 1
}

@test "scripts/_exit_statuses_for_cog.statuses() returns enum-aligned pairs" {
  python3 -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/scripts')
import _exit_statuses_for_cog as E
pairs = E.statuses()
assert pairs, 'statuses() returned empty list'
keys = [k for k, _ in pairs]
assert len(keys) == len(set(keys)), 'duplicate status keys in YAML'
import json
schema = json.loads(open('${REPO_ROOT}/templates/state.schema.json').read())
enum = set(schema['properties']['status']['enum'])
assert set(keys) == enum, f'YAML keys {set(keys)} != schema enum {enum}'
" || return 1
}
