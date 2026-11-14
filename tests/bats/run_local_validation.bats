#!/usr/bin/env bats

load test_helper

setup() {
  make_tmp_repo
}

@test "exits 2 when no recognized stack" {
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 2 ]]
  [[ "$output" == *"no recognized stack"* ]]
}

@test "node stack with passing test exits 0" {
  cat > package.json <<'EOF'
{ "name": "t", "scripts": { "test": "exit 0" } }
EOF
  # Need npm on PATH for the script to run; skip if absent.
  if ! command -v npm >/dev/null 2>&1; then skip "npm not installed"; fi
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
}

@test "node stack with failing test exits 3" {
  cat > package.json <<'EOF'
{ "name": "t", "scripts": { "test": "echo BOOM && exit 1" } }
EOF
  if ! command -v npm >/dev/null 2>&1; then skip "npm not installed"; fi
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 3 ]]
  [[ "$output" == *"npm run test"* ]]
}

@test "exits 1 outside a git repo" {
  cd "${BATS_TEST_TMPDIR}"
  rm -rf not-a-repo
  mkdir not-a-repo
  cd not-a-repo
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
}

@test "node stack with no PM on PATH is a setup error (exit 1)" {
  cat > package.json <<'EOF'
{ "name": "t" }
EOF
  git add package.json
  git commit -q -m "add package.json"
  # Empty PATH so no PM can be found, but keep coreutils available via absolute
  # paths the script already uses (git is resolved via the repo, command builtin
  # works without PATH for itself, etc.).
  local p="${BATS_TEST_TMPDIR}/no-pm"
  mkdir -p "$p"
  for cmd in bash git sed awk grep; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  PATH="$p" run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"setup-error"* ]]
}

@test "pnpm-lock.yaml without pnpm is a setup error (exit 1)" {
  cat > package.json <<'EOF'
{ "name": "t", "scripts": { "test": "exit 0" } }
EOF
  : > pnpm-lock.yaml
  git add package.json pnpm-lock.yaml
  git commit -q -m "add lockfile"
  local p="${BATS_TEST_TMPDIR}/no-pnpm"
  mkdir -p "$p"
  # provide npm and friends but NOT pnpm; the script must refuse to fall back to npm.
  for cmd in bash git sed awk grep npm; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  PATH="$p" run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"pnpm-lock.yaml"* ]]
}

@test "yarn.lock without yarn is a setup error (exit 1)" {
  cat > package.json <<'EOF'
{ "name": "t", "scripts": { "test": "exit 0" } }
EOF
  : > yarn.lock
  git add package.json yarn.lock
  git commit -q -m "add yarn lockfile"
  local p="${BATS_TEST_TMPDIR}/no-yarn"
  mkdir -p "$p"
  # provide npm but NOT yarn; the script must refuse to fall back to npm.
  for cmd in bash git sed awk grep npm; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  PATH="$p" run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"yarn.lock"* ]]
}

@test "python stack with passing pytest exits 0" {
  : > pyproject.toml
  stub_cmd pytest 'exit 0'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
}

@test "python stack with failing pytest exits 3" {
  : > pyproject.toml
  stub_cmd pytest 'echo BOOM; exit 1'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 3 ]]
  [[ "$output" == *"pytest"* ]]
}

@test "python stack with pytest exit 5 (no tests collected) exits 0" {
  : > pyproject.toml
  stub_cmd pytest 'echo "no tests ran"; exit 5'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"# skip: pytest (exit 5)"* ]]
  [[ "$output" != *"# fail: pytest"* ]]
}

@test "python stack with no py tools on PATH is a setup error (exit 1)" {
  : > pyproject.toml
  git add pyproject.toml
  git commit -q -m "add pyproject.toml"
  local p="${BATS_TEST_TMPDIR}/no-py"
  mkdir -p "$p"
  for cmd in bash git sed awk grep; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  PATH="$p" run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"no runnable Python validators"* ]]
  [[ "$output" == *"pytest not on PATH"* ]]
  [[ "$output" == *"ruff not on PATH"* ]]
  [[ "$output" == *"mypy not on PATH"* ]]
}

@test "python stack: mypy runs when [tool.mypy] section present" {
  cat > pyproject.toml <<'EOF'
[tool.mypy]
strict = true
EOF
  stub_cmd pytest 'exit 0'
  stub_cmd mypy 'exit 0'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"pass: mypy"* ]]
}

@test "python stack: mypy skipped when no [tool.mypy] section" {
  cat > pyproject.toml <<'EOF'
[project]
name = "x"
EOF
  stub_cmd pytest 'exit 0'
  # mypy stubbed to fail; if it were called, the overall run would exit 3.
  stub_cmd mypy 'echo "should not be called"; exit 1'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" != *"pass: mypy"* ]]
  [[ "$output" != *"fail: mypy"* ]]
}

@test "go stack with go not on PATH is a setup error (exit 1)" {
  : > go.mod
  git add go.mod
  git commit -q -m "add go.mod"
  local p="${BATS_TEST_TMPDIR}/no-go"
  mkdir -p "$p"
  for cmd in bash git sed awk grep; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  PATH="$p" run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"go.mod present but go not on PATH"* ]]
}

@test "go stack with passing go test exits 0" {
  : > go.mod
  stub_cmd go 'exit 0'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
}

@test "go stack with failing go test exits 3" {
  : > go.mod
  stub_cmd go 'echo BOOM; exit 1'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 3 ]]
  [[ "$output" == *"go test"* ]]
}

@test "rust stack with cargo not on PATH is a setup error (exit 1)" {
  : > Cargo.toml
  git add Cargo.toml
  git commit -q -m "add Cargo.toml"
  local p="${BATS_TEST_TMPDIR}/no-cargo"
  mkdir -p "$p"
  for cmd in bash git sed awk grep; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  PATH="$p" run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"Cargo.toml present but cargo not on PATH"* ]]
}

@test "rust stack with passing cargo test exits 0" {
  : > Cargo.toml
  stub_cmd cargo 'exit 0'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
}

@test "rust stack with failing cargo test exits 3" {
  : > Cargo.toml
  stub_cmd cargo 'echo BOOM; exit 1'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 3 ]]
  [[ "$output" == *"cargo test"* ]]
}

@test "ruby stack with bundle not on PATH is a setup error (exit 1)" {
  : > Gemfile
  git add Gemfile
  git commit -q -m "add Gemfile"
  local p="${BATS_TEST_TMPDIR}/no-bundle"
  mkdir -p "$p"
  for cmd in bash git sed awk grep; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  PATH="$p" run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"Gemfile present but bundle not on PATH"* ]]
}

@test "ruby stack with passing rspec exits 0" {
  : > Gemfile
  mkdir spec
  stub_cmd bundle 'exit 0'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
}

@test "ruby stack with failing rspec exits 3" {
  : > Gemfile
  mkdir spec
  stub_cmd bundle 'echo BOOM; exit 1'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 3 ]]
  [[ "$output" == *"rspec"* ]]
}

@test "rust stack: clippy runs and is reported on pass" {
  : > Cargo.toml
  stub_cmd cargo 'exit 0'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"pass: cargo clippy"* ]]
}

@test "rust stack: clippy failure (cargo test passes) exits 3" {
  : > Cargo.toml
  stub_cmd cargo '
if [[ "$1" == "clippy" && "$2" == "--no-deps" ]]; then echo "warn"; exit 1; fi
exit 0'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 3 ]]
  [[ "$output" == *"cargo clippy"* ]]
}

@test "ruby stack: rubocop failure exits 3" {
  : > Gemfile
  mkdir spec
  : > .rubocop.yml
  stub_cmd bundle '
if [[ "$1" == "exec" && "$2" == "rubocop" ]]; then echo "offense"; exit 1; fi
exit 0'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 3 ]]
  [[ "$output" == *"rubocop"* ]]
}

@test "node stack: lint and typecheck scripts are invoked" {
  cat > package.json <<'EOF'
{ "name": "t", "scripts": { "test": "exit 0", "lint": "exit 0", "typecheck": "exit 0" } }
EOF
  if ! command -v npm >/dev/null 2>&1; then skip "npm not installed"; fi
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"pass: npm run lint"* ]]
  [[ "$output" == *"pass: npm run typecheck"* ]]
}

@test "pnpm stack passes --if-present before the script name" {
  cat > package.json <<'EOF'
{ "name": "t", "scripts": { "typecheck": "tsc" } }
EOF
  : > pnpm-lock.yaml
  local argv="${BATS_TEST_TMPDIR}/pnpm.argv"
  # real pnpm forwards a flag after the script name to the script itself.
  stub_cmd pnpm "echo \"\$*\" >> '${argv}'
for arg in \"\${@:3}\"; do
  if [[ \"\$arg\" == --if-present ]]; then echo \"TS5023: Unknown compiler option '--if-present'\" >&2; exit 1; fi
done
exit 0"
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
  grep -qx 'run --if-present typecheck' "$argv"
}

@test "node stack: malformed package.json is a setup error (exit 1)" {
  if ! command -v jq >/dev/null 2>&1; then skip "jq not installed"; fi
  printf '{not json' > package.json
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"package.json is not valid JSON"* ]]
}

@test "node stack: non-object .scripts is a setup error (exit 1)" {
  if ! command -v jq >/dev/null 2>&1; then skip "jq not installed"; fi
  cat > package.json <<'EOF'
{ "name": "t", "scripts": "oops" }
EOF
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"scripts must be an object"* ]]
}

@test "python stack: mypy runs when setup.cfg has [mypy] section" {
  : > pyproject.toml
  cat > setup.cfg <<'EOF'
[mypy]
ignore_missing_imports = True
EOF
  stub_cmd pytest 'exit 0'
  stub_cmd mypy 'exit 0'
  run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"pass: mypy"* ]]
}

@test "python stack: mypy installed but no config reports config-skip" {
  : > pyproject.toml
  git add pyproject.toml
  git commit -q -m "add pyproject.toml without mypy config"
  local p="${BATS_TEST_TMPDIR}/mypy-no-cfg"
  mkdir -p "$p"
  for cmd in bash git sed awk grep; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  cat > "$p/mypy" <<'EOFM'
#!/usr/bin/env bash
exit 0
EOFM
  chmod +x "$p/mypy"
  PATH="$p" run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 1 ]]
  [[ "$output" == *"no runnable Python validators"* ]]
  [[ "$output" == *"mypy installed but no [mypy]/[tool.mypy] section"* ]]
  [[ "$output" == *"pytest not on PATH"* ]]
  [[ "$output" == *"ruff not on PATH"* ]]
}

@test "yarn stack skips script-presence check when jq is unavailable" {
  cat > package.json <<'EOF'
{ "name": "t", "scripts": { "test": "exit 0" } }
EOF
  : > yarn.lock
  git add package.json yarn.lock
  git commit -q -m "add yarn lockfile"
  local p="${BATS_TEST_TMPDIR}/yarn-no-jq"
  mkdir -p "$p"
  # restricted PATH: coreutils + a yarn stub, but no jq
  for cmd in bash git sed awk grep; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ln -sf "$(command -v "$cmd")" "$p/$cmd"
    fi
  done
  cat > "$p/yarn" <<'EOFY'
#!/usr/bin/env bash
exit 0
EOFY
  chmod +x "$p/yarn"
  PATH="$p" run bash "${SCRIPTS}/run_local_validation.sh"
  [[ "$status" -eq 0 ]]
  [[ "$output" == *"jq required"* ]]
}
