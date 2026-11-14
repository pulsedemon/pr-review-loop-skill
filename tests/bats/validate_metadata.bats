#!/usr/bin/env bats

load test_helper

@test "validate_metadata passes on the real repo" {
  run python3 "${SCRIPTS}/validate_metadata.py"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"metadata ok"* ]]
}

@test "validate_metadata fails on bad state schema" {
  copy_skill_tree
  echo "not valid json" > "${BATS_TEST_TMPDIR}/skill/templates/state.schema.json"
  run python3 "${BATS_TEST_TMPDIR}/skill/scripts/validate_metadata.py"
  [[ "$status" -ne 0 ]]
  [[ "$output" == *"invalid JSON"* ]]
}

@test "validate_metadata fails when SKILL.md version is missing" {
  copy_skill_tree
  # Strip the version: line from the frontmatter
  sed -i.bak '/^version: /d' "${BATS_TEST_TMPDIR}/skill/SKILL.md"
  rm "${BATS_TEST_TMPDIR}/skill/SKILL.md.bak"
  run python3 "${BATS_TEST_TMPDIR}/skill/scripts/validate_metadata.py"
  [[ "$status" -ne 0 ]]
  [[ "$output" == *"missing or empty 'version'"* ]]
}

@test "validate_metadata fails when SKILL.md version is not semver" {
  copy_skill_tree
  sed -i.bak 's/^version: .*/version: not-a-version/' "${BATS_TEST_TMPDIR}/skill/SKILL.md"
  rm "${BATS_TEST_TMPDIR}/skill/SKILL.md.bak"
  run python3 "${BATS_TEST_TMPDIR}/skill/scripts/validate_metadata.py"
  [[ "$status" -ne 0 ]]
  [[ "$output" == *"semver"* ]]
}
