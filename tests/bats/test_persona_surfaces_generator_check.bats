#!/usr/bin/env bats

# Generator-check gate for persona-derived surfaces.
#
# scripts/regen-check.sh regenerates the SKILL.md "Reviewer personas"
# section (via cog) and the reviewer.enum in reviewers/output.schema.json
# (via scripts/regen_schema_enum.py) from reviewers/personas.yaml and
# diffs against the checked-in files. Drift exits non-zero with a
# unified diff and a hint to run scripts/regen.sh.
#
# This bats wraps that gate so a drifted PR fails locally with the same
# diagnostic CI prints, and adds a canary that pins the presence of the
# cog markers (without which `cog --check` would degenerate to a vacuous
# pass).

load test_helper

@test "scripts/regen-check.sh succeeds on the checked-in tree" {
  run bash "${REPO_ROOT}/scripts/regen-check.sh"
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
  # scripts/regen-check.sh invokes cog with @cogfiles.txt. If a refactor
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

@test "scripts/regen-check.sh invokes both cog and regen_schema_enum.py" {
  # regen-check.sh is the single CI gate for both managed surfaces.
  # If a refactor removes either invocation, the gate silently shrinks
  # to one surface and the other can drift undetected by CI.
  grep -qE 'cogapp' "${REPO_ROOT}/scripts/regen-check.sh" || {
    echo "scripts/regen-check.sh no longer invokes cogapp."
    echo "Without it, SKILL.md drift would not be detected by the CI gate."
    return 1
  }
  grep -qE 'regen_schema_enum\.py[^A-Za-z0-9_].*--check' "${REPO_ROOT}/scripts/regen-check.sh" || {
    echo "scripts/regen-check.sh no longer invokes regen_schema_enum.py --check."
    echo "Without it, reviewers/output.schema.json enum drift would not be detected."
    return 1
  }
}
