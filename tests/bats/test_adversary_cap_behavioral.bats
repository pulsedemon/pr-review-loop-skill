#!/usr/bin/env bats

load test_helper

@test "scripts/_adversary_caps.sh sources cleanly and exports ADVERSARY_CAP" {
  # regen-check.sh compares the generator's output with itself, so a
  # syntactically broken helper body passes it. sourcing the real helper and
  # comparing ADVERSARY_CAP with the manifest catches that.
  run bash -c "source '${REPO_ROOT}/scripts/_adversary_caps.sh' && echo \"\${ADVERSARY_CAP}\""
  [[ "$status" -eq 0 ]] || {
    echo "scripts/_adversary_caps.sh failed to source (exit $status). Output:"
    echo "$output"
    return 1
  }
  local cap
  cap=$(python3 -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1]))["cap"])' \
    "${REPO_ROOT}/manifests/adversary-caps.yaml")
  [[ "$output" == "$cap" ]] || {
    echo "ADVERSARY_CAP exported value is '$output'; manifests/adversary-caps.yaml says '$cap'."
    return 1
  }
}

# operator coverage runs end to end in test_cap_drift_guard_fires.bats; the
# test below keeps the boundary that stops the cap matching a longer number.

# CAP_REGEX must stay a single-line top-level assignment in tests/run.sh.
# an empty extraction fails here instead of matching everything.
_cap_regex() {
  local extracted
  extracted=$(grep -E "^CAP_REGEX=" "${REPO_ROOT}/tests/run.sh" \
    | head -1 | sed -E "s/^CAP_REGEX='(.*)'\$/\\1/")
  if [[ -z "$extracted" ]]; then
    echo "ERROR: could not extract CAP_REGEX from tests/run.sh." >&2
    echo "       Expected a top-level line of the form: CAP_REGEX='...'." >&2
    return 1
  fi
  printf '%s' "$extracted"
}

@test "CAP_REGEX does not match 'shallow_adversary_runs < 20'" {
  local cap_regex; cap_regex=$(_cap_regex) || return 1
  ! printf 'shallow_adversary_runs < 20\n' | grep -qE "$cap_regex"
}

@test "SKILL.md retains the forced shallow_adversary_runs cap" {
  # a legacy schema field alone does not establish an active runtime cap.
  local forced='\bshallow_adversary_runs\b.{0,120}(cap|counter)|(cap|counter).{0,120}\bshallow_adversary_runs\b'
  grep -qE "$forced" "${REPO_ROOT}/SKILL.md" || {
    echo "SKILL.md must mention shallow_adversary_runs within ~120 chars of 'cap' or 'counter' (forced-path counter)"
    return 1
  }
}
