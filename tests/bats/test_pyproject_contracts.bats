#!/usr/bin/env bats

load test_helper

@test "SKILL.md states the Python minimum pyproject.toml requires" {
  local required
  required=$(sed -n 's/^requires-python = ">=\([0-9.]*\)"$/\1/p' "${REPO_ROOT}/pyproject.toml")
  [[ -n "$required" ]] || {
    echo "pyproject.toml has no requires-python floor"
    return 1
  }
  grep -qF -- "- Python ${required}+ available as \`python3\`" "${REPO_ROOT}/SKILL.md" || {
    echo "SKILL.md preconditions do not name Python ${required}+, the floor in pyproject.toml"
    return 1
  }
}

@test "a bare pytest run skips retained evidence under docs/superpowers" {
  local root="${BATS_TEST_TMPDIR}/tree"
  mkdir -p "${root}/docs/superpowers/reviews/run" "${root}/suite"
  cp "${REPO_ROOT}/pyproject.toml" "${root}/pyproject.toml"
  printf 'def test_kept():\n    pass\n' >"${root}/suite/test_kept.py"
  printf 'def test_planted():\n    pass\n' >"${root}/docs/superpowers/reviews/run/test_planted.py"
  cd "$root"
  run python3 -m pytest --collect-only -q -p no:cacheprovider
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"test_kept"* ]]
  [[ "$output" != *"test_planted"* ]]
}
