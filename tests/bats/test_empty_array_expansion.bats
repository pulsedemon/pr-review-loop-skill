#!/usr/bin/env bats

# meta-test: bash 3.2, which macOS ships as /bin/bash, treats "${arr[@]}" on an
# empty array as an unbound-variable error under `set -u`. bash 4+ does not, and
# every CI job runs ubuntu, so nothing but a static check catches the regression.
# scripts/state_init.sh shipped broken on every macOS host for exactly this.
#
# scoped to arrays with an empty initializer (`NAME=()`). every other array in
# scripts/ has a static non-empty initializer and cannot reach the error.
#
# sourced _*.sh helpers are deliberately included, unlike the set-flags rule:
# their arrays expand in the caller's `set -u` shell, so the hazard is theirs too.

load test_helper

@test "empty-initialized arrays in scripts/ use the bash 3.2 safe expansion guard" {
  offenders=()
  while IFS= read -r -d '' path; do
    names=$(sed -nE 's/^[[:space:]]*(local[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=\(\)[[:space:]]*$/\2/p' "$path" | sort -u)
    [[ -n "$names" ]] || continue
    for name in $names; do
      for idx in '@' '*'; do
        bare="\${${name}[${idx}]}"
        guarded="\${${name}[${idx}]+\"\${${name}[${idx}]}\"}"
        # every guarded occurrence contains one bare occurrence, so the
        # difference is the unguarded count. `${#name[@]}` never matches bare,
        # which keeps count checks legal.
        total=$(grep -o -F "$bare" "$path" | wc -l | tr -d ' ')
        ok=$(grep -o -F "$guarded" "$path" | wc -l | tr -d ' ')
        if (( total - ok > 0 )); then
          offenders+=("${path#"${REPO_ROOT}/"} -> \$${name}[${idx}]")
        fi
      done
    done
  done < <(find "${SCRIPTS}" -maxdepth 1 -name '*.sh' -type f -print0)

  if (( ${#offenders[@]} > 0 )); then
    printf 'Unguarded empty-array expansion (fails on bash 3.2 under set -u).\n' >&2
    printf 'Use ${NAME[@]+"${NAME[@]}"}, as scripts/ci_wait.sh does:\n' >&2
    printf '  - %s\n' "${offenders[@]}" >&2
    return 1
  fi
}
