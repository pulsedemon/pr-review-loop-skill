#!/usr/bin/env bats

# The type_design reachability gate is load-bearing for the
# "documented constraint not expressed in the schema/type" blocker. The
# gate is described in two places: the inline blocker pattern and the
# Rules section. Both must survive accidental refactor deletion or the
# blocker degenerates into a false-positive on validators that aren't
# wired up to production code paths.
#
# Scenario 25 Check 6 covers the runtime behavior of the gate; this
# bats test covers the prompt text itself so a stray edit can't silently
# remove the gate language and survive CI.

load test_helper

@test "type_design.md keeps the 'non-test call site' reachability qualifier" {
  # Anchor on the full phrase so a stray "non-test" mention elsewhere
  # (e.g. a TODO or unrelated note) can't substitute for the actual gate
  # language.
  grep -qE 'non-test (call site|caller)' "${REPO_ROOT}/reviewers/type_design.md" || {
    echo "type_design.md no longer contains 'non-test call site' or 'non-test caller'"
    echo "  — the reachability gate qualifier was deleted or weakened"
    return 1
  }
}

@test "type_design.md keeps the 'validator unused in production' downgrade rationale" {
  # Same anchoring concern as above. The full phrase is the load-bearing
  # one; partial mentions don't constitute the gate.
  grep -qE 'validator unused in production' "${REPO_ROOT}/reviewers/type_design.md" || {
    echo "type_design.md no longer contains the literal 'validator unused in production'"
    echo "  — the dead-validator downgrade clause was deleted or paraphrased away"
    return 1
  }
}

@test "type_design.md pins downgrade direction: 'validator unused in production' lives in a downgrade context" {
  # Bare presence of the phrase doesn't prove the gate downgrades. A
  # malicious / mistaken edit could rewrite "downgrade to suggestion and
  # note 'validator unused in production.'" as "flag as blocker anyway —
  # the validator unused in production isn't a defence" and the existing
  # presence-only grep would still pass while the gate is functionally
  # inverted. Anchor on the direction word.
  #
  # Both call sites (inline blocker bullet + Rules section) say "downgrade
  # to `suggestion`" within the same sentence as the phrase. Assert at
  # least one such co-occurrence exists, scoped to a single line so an
  # unrelated "downgrade" elsewhere in the file can't substitute.
  grep -E 'downgrade to .?suggestion.? and note "validator unused in production' \
    "${REPO_ROOT}/reviewers/type_design.md" >/dev/null || {
    echo "type_design.md no longer pairs the gate phrase with 'downgrade to suggestion'"
    echo "  — the downgrade direction is no longer pinned; the gate could be silently inverted to escalate"
    return 1
  }
}

@test "type_design.md Rules section restates both gate phrases (not just the inline blocker bullet)" {
  # The Rules section (## Rules) is the persona's authoritative summary of
  # what to flag. If the inline blocker bullet drifts and the Rules
  # section says something else, the persona reading both gets a
  # contradiction. The Rules section must restate both gate phrases —
  # the reachability qualifier ("non-test caller" / "non-test call site")
  # and the downgrade rationale ("validator unused in production").
  local rules_section
  rules_section=$(awk '
    /^## Rules/ { capturing = 1; next }
    capturing && /^## / { capturing = 0 }
    capturing { print }
  ' "${REPO_ROOT}/reviewers/type_design.md")
  [[ -n "$rules_section" ]] || {
    echo "type_design.md no longer has a ## Rules section — the gate restate site is gone"
    return 1
  }
  echo "$rules_section" | grep -qE 'non-test (call site|caller)' || {
    echo "type_design.md ## Rules section no longer restates 'non-test call site|caller'"
    echo "  — the inline blocker bullet and Rules section can now silently diverge"
    return 1
  }
  echo "$rules_section" | grep -q 'validator unused in production' || {
    echo "type_design.md ## Rules section no longer restates 'validator unused in production'"
    echo "  — the inline blocker bullet and Rules section can now silently diverge"
    return 1
  }
}

@test "type_design.md gate is co-located with the 'Documented constraint not expressed' blocker" {
  # Both gate phrases must appear on the same bullet line as the blocker
  # pattern. Otherwise a maintainer could relocate the gate language to a
  # ## Notes section while deleting the inline framing — the standalone
  # phrase greps above would still pass, but the blocker would be
  # functionally degraded (gate no longer visible to the persona at the
  # moment of flagging).
  local line
  line=$(grep "Documented constraint not expressed" "${REPO_ROOT}/reviewers/type_design.md" | head -1)
  [[ -n "$line" ]] || {
    echo "type_design.md no longer has the 'Documented constraint not expressed' blocker bullet"
    return 1
  }
  echo "$line" | grep -qE 'non-test (call site|caller)' || {
    echo "Gate qualifier 'non-test (call site|caller)' is no longer on the blocker bullet"
    echo "  blocker bullet: $line"
    return 1
  }
  echo "$line" | grep -q 'validator unused in production' || {
    echo "Gate downgrade rationale 'validator unused in production' is no longer on the blocker bullet"
    echo "  blocker bullet: $line"
    return 1
  }
}
