#!/usr/bin/env bash
# run_local_validation.sh — detect repo stack and run its standard validation suite.
#
# Replaces the inlined "detect project type and run appropriate commands" snippet
# in SKILL.md §4f. Deterministic, scripted, exit-coded.
#
# Usage:
#   run_local_validation.sh
#
# Exits:
#   0  — all detected validators passed (or nothing to run for a recognized stack)
#   1  — harness/setup error: cwd not a repo, internal error, or a stack was
#        detected (e.g. package.json, go.mod, Cargo.toml, Gemfile, pyproject.toml)
#        but the required toolchain is not on PATH. Treated as SETUP_ERROR by
#        the caller — a false-green is worse than a clear failure.
#   2  — no recognized stack (treat as soft pass; skill should log and continue)
#   3+ — a validator failed; tail of its output is on stderr
#
# stderr carries a "# stack: <name>" line per detected stack, then either
# "# pass: <command>" per success or "# fail: <command> (exit <N>)" plus the
# tail of stdout/stderr from the failing command. Stdout is silent on success
# and emits the failing command name on failure.

set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository." >&2
  exit 1
fi

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT" || exit 1

# Capture combined stdout+stderr of a command, tail the last 50 lines to stderr
# on failure (with a header), echo a one-line pass/fail marker to stderr. Returns
# the command's exit code (or 0 if the code is listed in RUN_CHECK_OK_RCS, a
# space-separated list of additional "OK" exit codes, e.g. pytest's 5 = "no
# tests collected").
run_check() {
  local desc="$1"
  shift
  local out rc ok_rc
  out=$("$@" 2>&1)
  rc=$?
  if [[ "$rc" -eq 0 ]]; then
    echo "# pass: $desc" >&2
    return 0
  fi
  for ok_rc in ${RUN_CHECK_OK_RCS:-}; do
    if [[ "$rc" -eq "$ok_rc" ]]; then
      echo "# skip: $desc (exit $rc)" >&2
      return 0
    fi
  done
  echo "# fail: $desc (exit $rc)" >&2
  echo "$out" | tail -n 50 >&2
  echo "# end fail: $desc" >&2
  return "$rc"
}

DETECTED=0
FIRST_FAIL=""

note_fail() {
  if [[ -z "$FIRST_FAIL" ]]; then
    FIRST_FAIL="$1"
  fi
}

# ---- Node / JS ----
if [[ -f package.json ]]; then
  DETECTED=$((DETECTED + 1))
  echo "# stack: node" >&2
  # If jq is available, validate package.json's structure once. A malformed
  # package.json or non-object .scripts otherwise slips past the yarn branch's
  # `jq -e .scripts[$s]` test (any jq error → "script absent" → silent skip),
  # while npm/pnpm would fail loudly. Treat both cases as setup errors.
  if command -v jq >/dev/null 2>&1; then
    if ! jq -e '.' package.json >/dev/null 2>&1; then
      echo "# setup-error: package.json is not valid JSON" >&2
      exit 1
    fi
    scripts_type=$(jq -r '.scripts | type' package.json)
    if [[ "$scripts_type" != "object" && "$scripts_type" != "null" ]]; then
      echo "# setup-error: package.json .scripts must be an object (got $scripts_type)" >&2
      exit 1
    fi
  fi
  PM=""
  if [[ -f pnpm-lock.yaml ]]; then
    if command -v pnpm >/dev/null 2>&1; then
      PM=pnpm
    else
      echo "# setup-error: pnpm-lock.yaml present but pnpm not on PATH; refusing to fall back to npm" >&2
      exit 1
    fi
  elif [[ -f yarn.lock ]]; then
    if command -v yarn >/dev/null 2>&1; then
      PM=yarn
    else
      echo "# setup-error: yarn.lock present but yarn not on PATH; refusing to fall back to npm" >&2
      exit 1
    fi
  elif command -v npm >/dev/null 2>&1; then
    PM=npm
  fi
  if [[ -z "$PM" ]]; then
    echo "# setup-error: node stack detected but no package manager on PATH" >&2
    exit 1
  fi
  # yarn does not honor `--if-present`; check the script exists before invoking.
  run_node_script() {
    local script="$1"
    if [[ "$PM" == "yarn" ]]; then
      if ! command -v jq >/dev/null 2>&1; then
        echo "# skip: $PM run $script (jq required to detect script presence under yarn)" >&2
        return 0
      fi
      if ! jq -e --arg s "$script" '.scripts[$s] // empty' package.json >/dev/null 2>&1; then
        echo "# skip: no \"$script\" script in package.json" >&2
        return 0
      fi
      run_check "$PM $script" "$PM" "$script" || note_fail "$PM $script"
    else
      # --if-present goes before the script name; pnpm forwards later flags to the script.
      run_check "$PM run $script" "$PM" run --if-present "$script" || note_fail "$PM run $script"
    fi
  }
  run_node_script test
  run_node_script lint
  run_node_script typecheck
fi

# ---- Python ----
if [[ -f pyproject.toml || -f setup.py || -f setup.cfg ]]; then
  DETECTED=$((DETECTED + 1))
  echo "# stack: python" >&2
  PY_RAN=0
  PY_REASONS=()
  if command -v pytest >/dev/null 2>&1; then
    PY_RAN=1
    # pytest exit 5 = "no tests collected". Happens when a repo has
    # pyproject.toml only for tooling config (e.g. ruff) and tests live
    # elsewhere (bats, etc). Treat as pass, not regression.
    RUN_CHECK_OK_RCS=5 run_check "pytest" pytest -q || note_fail "pytest"
  else
    PY_REASONS+=("pytest not on PATH")
  fi
  if command -v ruff >/dev/null 2>&1; then
    PY_RAN=1
    run_check "ruff check" ruff check . || note_fail "ruff check"
  else
    PY_REASONS+=("ruff not on PATH")
  fi
  if command -v mypy >/dev/null 2>&1; then
    mypy_files=()
    [[ -f pyproject.toml ]] && mypy_files+=(pyproject.toml)
    [[ -f mypy.ini ]] && mypy_files+=(mypy.ini)
    [[ -f setup.cfg ]] && mypy_files+=(setup.cfg)
    if ((${#mypy_files[@]} > 0)) && grep -q '\[tool\.mypy\]\|\[mypy\]' ${mypy_files[@]+"${mypy_files[@]}"}; then
      PY_RAN=1
      run_check "mypy" mypy . || note_fail "mypy"
    else
      PY_REASONS+=("mypy installed but no [mypy]/[tool.mypy] section in pyproject.toml/mypy.ini/setup.cfg")
    fi
  else
    PY_REASONS+=("mypy not on PATH")
  fi
  if [[ "$PY_RAN" -eq 0 ]]; then
    echo "# setup-error: no runnable Python validators (${PY_REASONS[*]+"${PY_REASONS[*]}"})" >&2
    exit 1
  fi
fi

# ---- Go ----
if [[ -f go.mod ]]; then
  DETECTED=$((DETECTED + 1))
  echo "# stack: go" >&2
  if ! command -v go >/dev/null 2>&1; then
    echo "# setup-error: go.mod present but go not on PATH" >&2
    exit 1
  fi
  run_check "go test ./..." go test ./... || note_fail "go test"
  run_check "go vet ./..." go vet ./... || note_fail "go vet"
fi

# ---- Rust ----
if [[ -f Cargo.toml ]]; then
  DETECTED=$((DETECTED + 1))
  echo "# stack: rust" >&2
  if ! command -v cargo >/dev/null 2>&1; then
    echo "# setup-error: Cargo.toml present but cargo not on PATH" >&2
    exit 1
  fi
  run_check "cargo test" cargo test --quiet || note_fail "cargo test"
  if cargo clippy --help >/dev/null 2>&1; then
    run_check "cargo clippy" cargo clippy --no-deps -- -D warnings || note_fail "cargo clippy"
  fi
fi

# ---- Ruby ----
if [[ -f Gemfile ]]; then
  DETECTED=$((DETECTED + 1))
  echo "# stack: ruby" >&2
  if ! command -v bundle >/dev/null 2>&1; then
    echo "# setup-error: Gemfile present but bundle not on PATH" >&2
    exit 1
  fi
  if [[ -d spec ]]; then
    run_check "bundle exec rspec" bundle exec rspec || note_fail "rspec"
  fi
  if [[ -f .rubocop.yml ]]; then
    run_check "bundle exec rubocop" bundle exec rubocop || note_fail "rubocop"
  fi
fi

if [[ "$DETECTED" -eq 0 ]]; then
  echo "# no recognized stack" >&2
  exit 2
fi

if [[ -n "$FIRST_FAIL" ]]; then
  # Any validator failure maps to exit 3. Failing commands and their tails are
  # already on stderr via run_check; stdout carries the first failing name.
  echo "$FIRST_FAIL"
  exit 3
fi

exit 0
