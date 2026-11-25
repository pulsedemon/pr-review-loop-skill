#!/usr/bin/env bats

load test_helper

@test "scripts/regen.sh exists and is executable" {
  [[ -x "${REPO_ROOT}/scripts/regen.sh" ]] || {
    echo "scripts/regen.sh missing or not executable"
    return 1
  }
}

@test "scripts/regen-check.sh exists and is executable" {
  [[ -x "${REPO_ROOT}/scripts/regen-check.sh" ]] || {
    echo "scripts/regen-check.sh missing or not executable"
    return 1
  }
}

# Records each python3 call instead of running it, so these tests see what
# regen.sh runs and change nothing. The cog call prints to stdout, as
# cog --diff does.
record_python3() {
  CALLS="${BATS_TEST_TMPDIR}/python3-calls"
  stub_cmd python3 "printf '%s\n' \"\$*\" >>'${CALLS}'
if [[ \"\$1 \$2\" == '-m cogapp' ]]; then echo 'cog output'; fi"
}

# Fails unless every scripts/regen_*.py ran with the given mode flag.
assert_every_generator_ran() {
  local mode="$1" generator
  for generator in "${REPO_ROOT}"/scripts/regen_*.py; do
    grep -qE "/scripts/$(basename "$generator") ${mode}\$" "$CALLS" || {
      echo "$(basename "$generator") did not run with ${mode}; calls:"
      cat "$CALLS"
      return 1
    }
  done
}

@test "regen.sh --check runs cog and every generator in check mode" {
  bats_require_minimum_version 1.5.0
  record_python3
  cd "$REPO_ROOT"
  run --separate-stderr bash scripts/regen.sh --check
  [[ "$status" -eq 0 ]]
  grep -qE '^-m cogapp --check --diff .*/scripts/cogfiles\.txt$' "$CALLS"
  assert_every_generator_ran --check
  grep -qE '/scripts/regen_panel_counts\.py --validate-markers$' "$CALLS"
  grep -qE '/scripts/regen_panel_counts\.py --validate-coverage$' "$CALLS"
  # docs/generators.md promises drift output on stderr.
  [[ -z "$output" ]]
  [[ "$stderr" == *"cog output"* ]]
}

@test "regen.sh --check passes a generator's drift exit through" {
  # cog runs first, so drift it also sees cannot show a generator's status
  # being swallowed; this drift is visible to regen_dev_trees.py alone.
  stub_cmd python3 'if [[ "$*" == *"/scripts/regen_dev_trees.py --check" ]]; then exit 5; fi'
  cd "$REPO_ROOT"
  run bash scripts/regen.sh --check
  [[ "$status" -eq 5 ]]
}

@test "regen.sh runs cog and every generator in write mode" {
  record_python3
  cd "$REPO_ROOT"
  run bash scripts/regen.sh
  [[ "$status" -eq 0 ]]
  grep -qE '^-m cogapp -r .*/scripts/cogfiles\.txt$' "$CALLS"
  assert_every_generator_ran --write
}

@test "personas-regen.sh shim execs regen.sh" {
  local shim="${REPO_ROOT}/scripts/personas-regen.sh"
  [[ -x "$shim" ]] || { echo "shim missing: $shim"; return 1; }
  grep -qE 'exec .*/regen\.sh" "\$@"' "$shim" || {
    echo "personas-regen.sh shim must exec regen.sh and forward \$@"
    cat "$shim"
    return 1
  }
}

@test "personas-check.sh shim execs regen-check.sh" {
  local shim="${REPO_ROOT}/scripts/personas-check.sh"
  [[ -x "$shim" ]] || { echo "shim missing: $shim"; return 1; }
  grep -qE 'exec .*/regen-check\.sh" "\$@"' "$shim" || {
    echo "personas-check.sh shim must exec regen-check.sh and forward \$@"
    cat "$shim"
    return 1
  }
}

@test "personas-regen.sh shim has no logic (set + exec only)" {
  local body
  body=$(grep -vE '^\s*(#|$)' "${REPO_ROOT}/scripts/personas-regen.sh" | wc -l)
  [[ "$body" -le 2 ]] || {
    echo "personas-regen.sh shim must be set + exec only (got $body operative lines)"
    return 1
  }
  grep -qE '^\s*exec\s+"\$\(dirname -- "\$0"\)/regen\.sh"\s+"\$@"\s*$' \
    "${REPO_ROOT}/scripts/personas-regen.sh" || {
    echo "personas-regen.sh shim must exec regen.sh with \"\$@\""
    return 1
  }
}

@test "personas-check.sh shim has no logic (set + exec only)" {
  local body
  body=$(grep -vE '^\s*(#|$)' "${REPO_ROOT}/scripts/personas-check.sh" | wc -l)
  [[ "$body" -le 2 ]] || {
    echo "personas-check.sh shim must be set + exec only (got $body operative lines)"
    return 1
  }
  grep -qE '^\s*exec\s+"\$\(dirname -- "\$0"\)/regen-check\.sh"\s+"\$@"\s*$' \
    "${REPO_ROOT}/scripts/personas-check.sh" || {
    echo "personas-check.sh shim must exec regen-check.sh with \"\$@\""
    return 1
  }
}
