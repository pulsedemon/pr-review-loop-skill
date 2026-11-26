#!/usr/bin/env bats

# Scenario-validation sync guard. The manifest is the source of truth for
# which scenario files are CI-trusted, manually validated, or design-only.
# These tests make sure every scenario file is classified and that the
# human-readable status embedded in each scenario file matches the manifest.

load test_helper

MANIFEST_CLI="${SCRIPTS}/scenario_manifest.py"
STATUS_SECTION_CLI="${SCRIPTS}/scenario_validation.py"
SCENARIO_DIR="${REPO_ROOT}/tests/scenarios"

manifest_list_checked() {
  python3 "$MANIFEST_CLI" --list "$1"
}

scenario_status_section() {
  python3 "$STATUS_SECTION_CLI" --section "${SCENARIO_DIR}/$1"
}

for_each_output_line() {
  local lines="$1"
  local callback="$2"
  local line
  [[ -z "$lines" ]] && return 0
  while IFS= read -r line; do
    "$callback" "$line" || return 1
  done <<<"$lines"
}

check_ci_trusted_file() {
  local file="$1"
  run python3 "$MANIFEST_CLI" --proof-sources-for "$file"
  [[ "$status" -eq 0 ]] || {
    echo "failed to read proof sources for ${file}: $output"
    return 1
  }
  local proofs="$output"
  [[ -n "$proofs" ]] || {
    echo "${file} is ci_trusted but has no proof sources"
    return 1
  }
  run scenario_status_section "$file"
  [[ "$status" -eq 0 ]]
  local status_section="$output"
  while IFS= read -r proof; do
    [[ -f "${REPO_ROOT}/${proof}" ]] || {
      echo "${file} references missing proof source ${proof}"
      return 1
    }
    grep -qF "${proof}" <<<"$status_section" || {
      echo "${file} should reference proof source ${proof} in its validation status section"
      return 1
    }
  done <<<"$proofs"
}

check_manual_validated_file() {
  local file="$1"
  if ! grep -Eq '_[Vv]alidated with .*: PASS\._' "${SCENARIO_DIR}/${file}"; then
    echo "${file} is manual_validated but has no recorded validation marker"
    return 1
  fi
}

check_design_only_file() {
  local file="$1"
  run scenario_status_section "$file"
  [[ "$status" -eq 0 ]]
  grep -q '^\*\*Missing evidence:\*\* ' <<<"$output" || {
    echo "${file} is design_only but is missing a '**Missing evidence:**' line"
    return 1
  }
}

@test "scenario manifest covers every scenario markdown file" {
  run bash -c '
    diff -u \
      <(python3 "'"${MANIFEST_CLI}"'" --list all-files) \
      <(cd "'"${SCENARIO_DIR}"'" && printf "%s\n" *.md | sort)
  '
  [[ "$status" -eq 0 ]] || {
    echo "tests/scenarios/manifest.yaml is out of sync with tests/scenarios/*.md"
    echo "$output"
    return 1
  }
}

@test "every scenario file carries a validation status heading" {
  run manifest_list_checked all-files
  [[ "$status" -eq 0 ]]
  files="$output"
  while IFS= read -r file; do
    run scenario_status_section "$file"
    [[ "$status" -eq 0 ]] || {
      echo "$output"
      return 1
    }
  done <<<"$files"
}

@test "scenario file status lines match manifest tiers" {
  cd "$BATS_TEST_TMPDIR" || return 1
  run manifest_list_checked tier-map
  [[ "$status" -eq 0 ]]
  tier_map="$output"
  while IFS='|' read -r file tier; do
    run scenario_status_section "$file"
    [[ "$status" -eq 0 ]]
    grep -q "^\\*\\*Status:\\*\\* \`${tier}\`$" <<<"$output" || {
      echo "${file} does not declare **Status:** \`${tier}\`"
      return 1
    }
  done <<<"$tier_map"
}

@test "for_each_output_line skips empty input" {
  marker="${BATS_TEST_TMPDIR}/marker"
  touch_marker() {
    echo touched > "$marker"
  }

  for_each_output_line "" touch_marker
  [[ ! -e "$marker" ]]
}

@test "ci_trusted scenarios point at real proof sources" {
  run manifest_list_checked ci-files
  [[ "$status" -eq 0 ]]
  for_each_output_line "$output" check_ci_trusted_file
}

@test "manual_validated scenarios carry a recorded validation marker" {
  run manifest_list_checked manual-files
  [[ "$status" -eq 0 ]]
  for_each_output_line "$output" check_manual_validated_file
}

@test "design_only scenarios explain what evidence is still missing" {
  run manifest_list_checked design-files
  [[ "$status" -eq 0 ]]
  for_each_output_line "$output" check_design_only_file
}
