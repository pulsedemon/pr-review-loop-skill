#!/usr/bin/env bats

# Meta-test: every scripts/*.sh must declare `set -euo pipefail` in its
# header. Static check because every script handles its documented exit
# codes explicitly, so dropping `-e` would not change any behavior test's
# outcome — only a grep can catch the regression.
#
# Exemption: scripts/_*.sh are sourced helpers (not executed). `set -e` in
# a sourced file leaks into the caller's shell, so the convention is the
# opposite for these — they MUST NOT declare it. They are skipped here.

load test_helper

@test "every scripts/*.sh (except sourced _*.sh helpers) declares set -euo pipefail" {
  missing=()
  while IFS= read -r -d '' path; do
    if ! grep -qE '^set -euo pipefail\b' "$path"; then
      missing+=("$path")
    fi
  done < <(find "${SCRIPTS}" -maxdepth 1 -name '*.sh' -not -name '_*.sh' -type f -print0)

  if (( ${#missing[@]} > 0 )); then
    printf 'Missing `set -euo pipefail` in:\n' >&2
    printf '  - %s\n' "${missing[@]}" >&2
    return 1
  fi
}
