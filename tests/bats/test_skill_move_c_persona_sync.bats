#!/usr/bin/env bats

# regen-check compares output with its renderer; these checks retain the
# severity rules and the manifest's ownership relationship across both.

load test_helper

@test "SKILL.md Move C preserves severity and configured ownership" {
  local skill_line owner cross_ref ownership expected
  skill_line=$(grep "^- \*\*Move C" "${REPO_ROOT}/SKILL.md")
  owner=$(python3 "${SCRIPTS}/personas_manifest.py" --list schema-constraint-owner)
  cross_ref=$(printf 'cross-reference `%s` in `detail`' "$owner")
  ownership=$(printf '`%s` owns the blocker' "$owner")
  local expectations=(
    'terminology drift (blocker)'
    'schema-constraint bullet always suggestion'
    "$cross_ref"
    "$ownership"
    'blocker if doc-as-contract'
  )
  for expected in "${expectations[@]}"; do
    if ! grep -Fq -- "$expected" <<<"$skill_line"; then
      echo "SKILL.md Move C missing: $expected"
      echo "  bullet: $skill_line"
      return 1
    fi
  done
}
