#!/usr/bin/env bats

# Negative-side coverage for the §4d.0 cap-drift guard in tests/run.sh.
#
# The companion file tests/bats/test_adversary_cap_behavioral.bats only
# asserts positive properties (helper sourceability + ADVERSARY_CAP value,
# CAP_REGEX matches/non-matches, SKILL.md dual-counter proximity). The
# schema-maxima mirror surface is now owned by scripts/regen_adversary_caps.py
# (which writes both maxima from manifests/adversary-caps.yaml).
# Nothing else exercises the guard's failure path — its allow-listing and
# exit logic in the violation loop (the `while IFS= read -r hit` block in
# tests/run.sh). A refactor that broke the violation loop would silently
# let prose drift in: the positive-control count-pin near the bottom of
# the prelude (`grep -cE "$CAP_REGEX" tests/run.sh` against
# `EXPECTED_RUN_SH_CAP_MATCHES`) would still pass on the canonical
# paraphrases inside the CAP_REGEX block comment, but the allow-listing
# and exit logic would no longer flag actual violations.
#
# This is the only bats file that runs tests/run.sh as a subprocess. We
# shadow REPO_ROOT by copying the real run.sh into a tmp tree that
# symlinks the real repo contents — the guard scans the tmp tree, exits
# 3 on the injected violation, and never reaches the `exec bats` tail.

load test_helper

setup() {
  TMP_REPO="${BATS_TEST_TMPDIR}/repo"
  mkdir -p "${TMP_REPO}/tests" "${TMP_REPO}/docs"
  # symlink the dirs the guard scans so allow-listed paths resolve identically
  ln -s "${REPO_ROOT}/docs/adversary.md" "${TMP_REPO}/docs/adversary.md"
  ln -s "${REPO_ROOT}/templates"          "${TMP_REPO}/templates"
  ln -s "${REPO_ROOT}/scripts"            "${TMP_REPO}/scripts"
  ln -s "${REPO_ROOT}/SKILL.md"           "${TMP_REPO}/SKILL.md"
  # symlink remaining doc tree so excluded-by-design dirs still exist
  ln -s "${REPO_ROOT}/docs/synthesis.md"    "${TMP_REPO}/docs/synthesis.md"
  # docs/superpowers/, tests/scenarios/, and tools/recall-harness/ are all
  # excluded-by-design prefixes. Create them as real (empty) directories rather
  # than symlinking to the real repo — a fixture write under a symlinked dir
  # resolves through the symlink and pollutes the real working tree.
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
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "expected guard error message in output, got: $output"
    return 1
  }
  [[ "$output" == *"note.md"* ]] || {
    echo "expected violating file path in output, got: $output"
    return 1
  }
}

@test "cap-drift guard does not flag the allow-listed canonical paths" {
  # No injected violation. The guard should not produce its violation message.
  # We can't run the whole script (the `exec bats` tail would recurse), so
  # source the guard block via a wrapper that stops before the tail.
  #
  # Simpler: invoke run.sh and let it exec bats against the empty bats dir.
  # bats with no test files exits 0 (no tests is not a failure in 1.7+).
  run bash "${TMP_REPO}/tests/run.sh"
  # Pin exit status: a clean tree must pass the entire run.sh prelude, not
  # just the cap-drift sub-check. Without this assertion an unrelated drift
  # guard exiting 3 would silently pass this test as long as the cap-drift
  # error string happened not to appear.
  [[ "$status" -eq 0 ]] || {
    echo "expected exit 0 on clean tree, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" != *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "guard fired unexpectedly on clean tree: $output"
    return 1
  }
}

@test "cap-drift guard fires on shallow_approval_adversary_runs == 2 (second alternation, == operator)" {
  printf '%s\n' 'doc note: shallow_approval_adversary_runs == 2' \
    > "${TMP_REPO}/approval-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "expected guard error message in output, got: $output"
    return 1
  }
  [[ "$output" == *"approval-note.md"* ]] || {
    echo "expected violating file path in output, got: $output"
    return 1
  }
}

@test "cap-drift guard fires on shallow_adversary_runs <= 2 (<= operator)" {
  printf '%s\n' 'doc note: shallow_adversary_runs <= 2' \
    > "${TMP_REPO}/le-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "expected guard error message in output, got: $output"
    return 1
  }
  [[ "$output" == *"le-note.md"* ]] || {
    echo "expected violating file path in output, got: $output"
    return 1
  }
}

@test "cap-drift guard fires on shallow_adversary_runs > 2 (> operator)" {
  # CAP_REGEX accepts [<>=]{1,2}; tests/run.sh documents `>= 2` as a paraphrase
  # the guard catches. Without a fixture covering `>` / `>=`, a regex regression
  # to `[<=]{1,2}` would silently pass — the positive-control assertion only
  # needs one match in tests/run.sh's own examples to stay green.
  printf '%s\n' 'doc note: shallow_adversary_runs > 2' \
    > "${TMP_REPO}/gt-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "expected guard error message in output, got: $output"
    return 1
  }
  [[ "$output" == *"gt-note.md"* ]] || {
    echo "expected violating file path in output, got: $output"
    return 1
  }
}

@test "cap-drift guard fires on shallow_approval_adversary_runs >= 2 (>= operator)" {
  printf '%s\n' 'doc note: shallow_approval_adversary_runs >= 2' \
    > "${TMP_REPO}/ge-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "expected guard error message in output, got: $output"
    return 1
  }
  [[ "$output" == *"ge-note.md"* ]] || {
    echo "expected violating file path in output, got: $output"
    return 1
  }
}

# Per-prefix tests below: each writes exactly one fixture under one excluded
# prefix. A combined test (all three at once) would still pass if a single
# prefix were dropped from EXCLUDED_CAP_PREFIXES — the remaining two would
# absorb the assertion. Splitting forces an independent failure per prefix.

@test "cap-drift guard does NOT fire on violation under docs/superpowers/" {
  printf '%s\n' 'frozen spec quote: shallow_adversary_runs < 2' \
    > "${TMP_REPO}/docs/superpowers/sp-fixture.md"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -ne 3 ]] || {
    echo "guard exited 3 on docs/superpowers/ fixture; exclusion regressed"
    echo "output: $output"
    return 1
  }
  [[ "$output" != *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "guard fired on docs/superpowers/ fixture; exclusion regressed: $output"
    return 1
  }
}

@test "cap-drift guard does NOT fire on violation under tests/scenarios/" {
  printf '%s\n' 'scenario expectation: shallow_approval_adversary_runs == 2' \
    > "${TMP_REPO}/tests/scenarios/sc-fixture.md"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -ne 3 ]] || {
    echo "guard exited 3 on tests/scenarios/ fixture; exclusion regressed"
    echo "output: $output"
    return 1
  }
  [[ "$output" != *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "guard fired on tests/scenarios/ fixture; exclusion regressed: $output"
    return 1
  }
}

@test "cap-drift guard does NOT fire on violation under tools/recall-harness/" {
  printf '%s\n' 'real-miss quote: shallow_adversary_runs <= 2' \
    > "${TMP_REPO}/tools/recall-harness/rh-fixture.md"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -ne 3 ]] || {
    echo "guard exited 3 on tools/recall-harness/ fixture; exclusion regressed"
    echo "output: $output"
    return 1
  }
  [[ "$output" != *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "guard fired on tools/recall-harness/ fixture; exclusion regressed: $output"
    return 1
  }
}

@test "cap-drift guard does NOT scan local .worktrees/" {
  mkdir -p "${TMP_REPO}/.worktrees/manual-scenario-validation/tests"
  printf '%s\n' 'stale copy: shallow_adversary_runs < 2' \
    > "${TMP_REPO}/.worktrees/manual-scenario-validation/tests/run.sh"

  run bash "${TMP_REPO}/tests/run.sh"

  [[ "$status" -eq 0 ]] || {
    echo "expected exit 0 with ignored .worktrees fixture, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" != *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "guard fired on .worktrees fixture; exclusion regressed: $output"
    return 1
  }
}

@test "cap-drift guard fires on shallow_adversary_runs<2 (zero-space, single-char operator)" {
  # Without {0,40} in CAP_REGEX (vs {1,40}), the zero-space single-char variant
  # would slip past the guard. This fixture pins the regex against that
  # regression.
  printf '%s\n' 'doc note: shallow_adversary_runs<2' \
    > "${TMP_REPO}/zerospace-note.md"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"adversary cap literal (2) appears next to cap field name"* ]] || {
    echo "expected guard error message in output, got: $output"
    return 1
  }
  [[ "$output" == *"zerospace-note.md"* ]] || {
    echo "expected violating file path in output, got: $output"
    return 1
  }
}

@test "positive control fires when CAP_REGEX is mutated so the example block no longer matches" {
  # The positive control in tests/run.sh count-pins CAP_REGEX matches in
  # tests/run.sh itself (currently 5, all in the block comment above CAP_REGEX).
  # If a future refactor deletes the positive-control block but leaves the
  # rest of the guard intact, the guard still flags external violations but
  # silently loses its protection against a regex that no longer matches the
  # canonical paraphrases. This test mutates CAP_REGEX so it matches none of
  # the comment examples and asserts the count-pin fires with its canonical
  # error string — failing loud if the positive control is ever removed or
  # weakened back to a bare `grep -q`.
  sed -i.bak -E "s|^CAP_REGEX='.*'|CAP_REGEX='__never_matches_anything_xyz__'|" \
    "${TMP_REPO}/tests/run.sh"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3 from positive control, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"CAP_REGEX matches; expected"* ]] || {
    echo "expected count-pin error string in output, got: $output"
    return 1
  }
}

@test "cap-drift guard fires on a sibling 'scenarios' dir outside tests/ (path-anchored exclusion)" {
  # The exclusion is anchored to the repo-relative prefix tests/scenarios/, not
  # the basename 'scenarios'. A sibling directory of the same name elsewhere in
  # the tree must still be scanned.
  mkdir -p "${TMP_REPO}/docs/scenarios"
  printf '%s\n' 'doc note: shallow_adversary_runs < 2' \
    > "${TMP_REPO}/docs/scenarios/sibling-fixture.md"
  run bash "${TMP_REPO}/tests/run.sh"
  [[ "$status" -eq 3 ]] || {
    echo "expected exit 3 on docs/scenarios/ violation, got $status"
    echo "output: $output"
    return 1
  }
  [[ "$output" == *"sibling-fixture.md"* ]] || {
    echo "expected violating file path in output, got: $output"
    return 1
  }
}
