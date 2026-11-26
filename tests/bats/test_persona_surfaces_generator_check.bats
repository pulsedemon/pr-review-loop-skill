#!/usr/bin/env bats

# Generator-check gate for manifest-derived surfaces.
#
# Runs scripts/regen-check.sh on the checked-in tree so a drifted PR fails
# locally with the diagnostic CI prints, and pins the SKILL.md cog markers
# and routing, without which cog --check passes with nothing to check.

load test_helper

@test "scripts/regen-check.sh succeeds on the UTF-8 tree in an ASCII locale" {
  run env LC_ALL=C PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 bash "${REPO_ROOT}/scripts/regen-check.sh"
  [[ "$status" -eq 0 ]] || {
    echo "scripts/regen-check.sh failed (exit $status). Output:"
    echo "$output"
    echo ""
    echo "Fix: run scripts/regen.sh and commit the result."
    return 1
  }
}

@test "cog markers are present in SKILL.md (canary against silent marker removal)" {
  # If a future refactor strips the cog markers from SKILL.md,
  # scripts/regen-check.sh would silently pass (cog has no managed
  # region to check). Pin the marker presence so that case fails loudly
  # with a clear diagnostic.
  grep -qF "<!--[[[cog" "${REPO_ROOT}/SKILL.md" || {
    echo "SKILL.md missing cog open marker '<!--[[[cog'"
    echo "Did a refactor strip the generator region around 'Reviewer personas'?"
    return 1
  }
  grep -qF "<!--[[[end]]]-->" "${REPO_ROOT}/SKILL.md" || {
    echo "SKILL.md missing cog end marker '<!--[[[end]]]-->'"
    return 1
  }
}

@test "scripts/cogfiles.txt routes cog at SKILL.md (canary against silent re-routing)" {
  # scripts/regen.sh invokes cog with @cogfiles.txt. If a refactor
  # empties cogfiles.txt or drops SKILL.md from it, cog --check exits 0 with
  # nothing checked — the cog markers canary above still passes, but cog is
  # no longer pointed at them. Pin the routing so that case fails loudly.
  grep -E '^[[:space:]]*SKILL\.md[[:space:]]*$' "${REPO_ROOT}/scripts/cogfiles.txt" >/dev/null || {
    echo "scripts/cogfiles.txt is missing a 'SKILL.md' entry."
    echo "Without it, scripts/regen-check.sh would silently pass while SKILL.md drifts."
    echo "Current contents:"
    cat "${REPO_ROOT}/scripts/cogfiles.txt"
    return 1
  }
}
