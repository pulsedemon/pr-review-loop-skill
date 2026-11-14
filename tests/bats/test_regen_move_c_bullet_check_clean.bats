#!/usr/bin/env bats

# Smoke tests for the §4b Move C bullet generator (Tier 1 PR-4).
# Pins three invariants:
#   1. scripts/regen-check.sh is clean — i.e. the cog block in SKILL.md
#      and the bullet currently in the file agree (no drift between
#      reviewers/personas.yaml and SKILL.md).
#   2. The renderer reaches personas.yaml via the typed loader, not
#      via an inlined yaml.safe_load. This protects the
#      single-source-of-truth contract: every persona surface flows
#      through scripts/personas_manifest.load_manifest.
#   3. The cog markers for the Move C block are present in SKILL.md
#      (canary against silent marker removal; per docs/generators.md rule #5).
#      Without this, a refactor that strips only the Move C markers would
#      leave regen-check.sh silently unchecking that region while the
#      generic marker canary in test_persona_surfaces_generator_check.bats
#      still passes (the Reviewer personas markers would remain).

load test_helper

@test "regen-check.sh is clean for the Move C bullet block" {
  bash "${REPO_ROOT}/scripts/regen-check.sh"
}

@test "the Move C bullet helper reads only personas.yaml via the typed loader" {
  grep -qE 'reviewers/personas\.yaml|personas_manifest|load_manifest' \
    "${REPO_ROOT}/scripts/_move_c_bullet_for_cog.py" || {
    echo "_move_c_bullet_for_cog.py must reach personas.yaml via load_manifest"
    return 1
  }
}

@test "Move C cog markers are present in SKILL.md (canary against silent marker removal)" {
  grep -qF 'import _move_c_bullet_for_cog' "${REPO_ROOT}/SKILL.md" || {
    echo "SKILL.md missing 'import _move_c_bullet_for_cog' — the Move C cog block's open marker was stripped"
    return 1
  }
}
