#!/usr/bin/env bats

# the violation loop and example-count pin protect different failures;
# either can break while the other still passes.

load test_helper

assert_guard_fires() {
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"appears next to cap field name outside allowed files"* ]] || {
    echo "expected guard error message in output, got: $output"
    return 1
  }
  [[ "$output" == *"$1"* ]] || {
    echo "expected violating file path '$1', got: $output"
    return 1
  }
}

assert_clean_exit() {
  [[ "$status" -eq 0 ]] || {
    echo "expected exit 0, got $status"
    echo "output: $output"
    return 1
  }
}

setup() {
  TMP_REPO="${BATS_TEST_TMPDIR}/repo"
  mkdir -p "${TMP_REPO}/tests" "${TMP_REPO}/docs" "${TMP_REPO}/manifests"
  # a fixture cap keeps operator and boundary coverage independent of the
  # cap currently shipped in the real manifest.
  printf 'cap: 2\n' >"${TMP_REPO}/manifests/adversary-caps.yaml"
  # symlink the dirs the guard scans so allow-listed paths resolve identically
  ln -s "${REPO_ROOT}/docs/adversary.md" "${TMP_REPO}/docs/adversary.md"
  ln -s "${REPO_ROOT}/templates"          "${TMP_REPO}/templates"
  ln -s "${REPO_ROOT}/scripts"            "${TMP_REPO}/scripts"
  ln -s "${REPO_ROOT}/SKILL.md"           "${TMP_REPO}/SKILL.md"
  ln -s "${REPO_ROOT}/docs/synthesis.md"    "${TMP_REPO}/docs/synthesis.md"
  # keep writable fixture directories real: symlinks would redirect planted
  # violations into the checkout.
  mkdir -p "${TMP_REPO}/docs/superpowers" \
           "${TMP_REPO}/tests/scenarios" \
           "${TMP_REPO}/tools/recall-harness"
  # copy run.sh so HERE resolves inside TMP_REPO/tests
  cp "${REPO_ROOT}/tests/run.sh" "${TMP_REPO}/tests/run.sh"
  # empty bats dir so the `exec bats` tail (if reached) finds nothing to do
  mkdir -p "${TMP_REPO}/tests/bats"
}

@test "cap-drift guard exits 3 when a violation is injected outside allowed paths" {
  printf '%s\n' 'doc note: shallow_adversary_runs < 2' \
    > "${TMP_REPO}/note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_guard_fires "note.md"
}

@test "cap-drift guard scans comparisons inside tests/run.sh" {
  printf '\n%s\n' '# shallow_adversary_runs < 2' >>"${TMP_REPO}/tests/run.sh"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_guard_fires "./tests/run.sh:"
}

@test "cap-drift guard does not flag the allow-listed canonical paths" {
  rm "${TMP_REPO}/docs/adversary.md" "${TMP_REPO}/templates"
  mkdir "${TMP_REPO}/templates"
  printf '%s\n' 'shallow_adversary_runs < 2' >"${TMP_REPO}/docs/adversary.md"
  printf '%s\n' '{"description": "shallow_approval_adversary_runs == 2"}' \
    >"${TMP_REPO}/templates/state.schema.json"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_clean_exit
}

@test "cap-drift guard fires on shallow_approval_adversary_runs == 2 (second alternation, == operator)" {
  printf '%s\n' 'doc note: shallow_approval_adversary_runs == 2' \
    > "${TMP_REPO}/approval-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_guard_fires "approval-note.md"
}

@test "cap-drift guard fires on shallow_adversary_runs <= 2 (<= operator)" {
  printf '%s\n' 'doc note: shallow_adversary_runs <= 2' \
    > "${TMP_REPO}/le-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_guard_fires "le-note.md"
}

@test "cap-drift guard fires on shallow_adversary_runs > 2 (> operator)" {
  # without a > fixture, [<=]{1,2} still matches >= through the equals sign.
  printf '%s\n' 'doc note: shallow_adversary_runs > 2' \
    > "${TMP_REPO}/gt-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_guard_fires "gt-note.md"
}

@test "cap-drift guard fires on shallow_approval_adversary_runs >= 2 (>= operator)" {
  printf '%s\n' 'doc note: shallow_approval_adversary_runs >= 2' \
    > "${TMP_REPO}/ge-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_guard_fires "ge-note.md"
}

@test "cap-drift guard does NOT fire on violation under docs/superpowers/" {
  printf '%s\n' 'frozen spec quote: shallow_adversary_runs < 2' \
    > "${TMP_REPO}/docs/superpowers/sp-fixture.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_clean_exit
}

@test "cap-drift guard does NOT fire on violation under tests/scenarios/" {
  printf '%s\n' 'scenario expectation: shallow_approval_adversary_runs == 2' \
    > "${TMP_REPO}/tests/scenarios/sc-fixture.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_clean_exit
}

@test "cap-drift guard does NOT fire on violation under tools/recall-harness/" {
  printf '%s\n' 'real-miss quote: shallow_adversary_runs <= 2' \
    > "${TMP_REPO}/tools/recall-harness/rh-fixture.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_clean_exit
}

@test "cap-drift guard does NOT scan local .worktrees/" {
  mkdir -p "${TMP_REPO}/.worktrees/manual-scenario-validation/tests"
  printf '%s\n' 'stale copy: shallow_adversary_runs < 2' \
    > "${TMP_REPO}/.worktrees/manual-scenario-validation/tests/run.sh"

  run bash "${TMP_REPO}/tests/run.sh"
  assert_clean_exit
}

@test "cap-drift guard fires on shallow_adversary_runs<2 (zero-space, single-char operator)" {
  # {1,40} would miss a comparison with no separator before its operator.
  printf '%s\n' 'doc note: shallow_adversary_runs<2' \
    > "${TMP_REPO}/zerospace-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_guard_fires "zerospace-note.md"
}

@test "positive control fires when CAP_REGEX_FORMAT is mutated so the examples no longer match" {
  # pin the count diagnostic separately from ordinary violation detection.
  sed -i.bak -E "s|^CAP_REGEX_FORMAT='.*'|CAP_REGEX_FORMAT='__never_matches_%s__'|" \
    "${TMP_REPO}/tests/run.sh"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3 from positive control, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"CAP_REGEX_FORMAT example matches; expected"* ]] || {
    echo "expected count-pin error string in output, got: $output"
    return 1
  }
}

@test "cap-drift guard flags the cap value the manifest sets" {
  printf 'cap: 3\n' >"${TMP_REPO}/manifests/adversary-caps.yaml"
  printf '%s\n' 'doc note: shallow_adversary_runs < 3' \
    >"${TMP_REPO}/cap3-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_guard_fires "cap3-note.md"
  [[ "$output" == *"adversary cap literal (3)"* ]] || {
    echo "expected the guard message to name cap 3, got: $output"
    return 1
  }
}

@test "cap-drift guard fires on a sibling 'scenarios' dir outside tests/ (path-anchored exclusion)" {
  # excluding the basename 'scenarios' would hide unrelated sibling paths.
  mkdir -p "${TMP_REPO}/docs/scenarios"
  printf '%s\n' 'doc note: shallow_adversary_runs < 2' \
    > "${TMP_REPO}/docs/scenarios/sibling-fixture.md"
  run bash "${TMP_REPO}/tests/run.sh"
  assert_guard_fires "sibling-fixture.md"
}

@test "run.sh drops the parallel flags on a one-core machine" {
  stub_cmd nproc 'echo 1'
  stub_cmd bats '[[ "$1" == --version ]] && { echo "Bats 1.13.0"; exit 0; }; echo "bats args: $*"'
  run bash "${TMP_REPO}/tests/run.sh"
  assert_clean_exit
  [[ "$output" == "bats args: ${TMP_REPO}/tests/bats" ]] || {
    echo "expected bats to get only the test directory, got: $output"
    return 1
  }
}
