#!/usr/bin/env bats

# Canary for the §4b procedure-move cog block in SKILL.md. Stripping only its
# markers stops cog from checking the block while the Reviewer personas
# markers pinned by test_persona_surfaces_generator_check.bats still pass.

load test_helper

@test "Move C cog markers are present in SKILL.md (canary against silent marker removal)" {
  grep -qF 'import _move_c_bullet_for_cog' "${REPO_ROOT}/SKILL.md" || {
    echo "SKILL.md missing 'import _move_c_bullet_for_cog' — the Move C cog block's open marker was stripped"
    return 1
  }
}
