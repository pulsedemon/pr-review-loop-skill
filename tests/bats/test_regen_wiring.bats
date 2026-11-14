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
