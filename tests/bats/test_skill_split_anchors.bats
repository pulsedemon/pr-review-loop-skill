#!/usr/bin/env bats

# Canary for the SKILL.md -> docs/synthesis.md + docs/adversary.md split.
# Promotes tests/scenarios/22-skill-split-anchors.md from a hand-run
# checklist to a CI-trusted contract.
#
# Pins:
#   1. SKILL.md does not carry the matcher rule literal. The rule lives in
#      docs/synthesis.md only; a copy in SKILL.md lets the two drift.
#   2. docs/synthesis.md keeps its three section anchors (Matcher,
#      Promotion paths, Demotion recording). SKILL.md and docs/adversary.md
#      deep-link to these, so a rename silently breaks those links.
#   3. docs/adversary.md links back to at least two synthesis anchors.
#   4. tests/run.sh still runs the matcher drift guard.
#
# Check 4 exists because scenario 22 pinned the guard by its old literal
# ("token_overlap >= 0.6") long after the guard was rewritten as a regex.
# The scenario reported a passing checklist while asserting a count of 2
# that had actually been 0 since the rewrite. tests/run.sh deliberately
# excludes tests/scenarios/ from its cap-drift grep ("test expectations,
# not contract prose"), so nothing caught it. Pin the guard by a fragment
# of its live regex, not by the threshold text it matches.
#
# Anchor-liveness: checks 2 and 4 grep for structure that later assertions
# depend on. Each fails loudly when its anchor stops matching rather than
# passing vacuously — the exact failure mode that let check 4 rot.
#
# Mutation-tested before requesting review:
#   - append the matcher literal to SKILL.md -> "does not carry the matcher
#     rule literal" fails.
#   - rename "## Matcher" to "## Matcher rules" in docs/synthesis.md ->
#     "keeps its three section anchors" fails.
#   - rewrite both synthesis.md#matcher / #promotion-paths backlinks to bare
#     synthesis.md -> "links back to the synthesis anchors" fails.
#   - point the run.sh guard regex at a pattern that matches nothing ->
#     both "still runs the matcher drift guard" and "actually fires on a
#     violation" fail.
#
# The liveness check re-runs the guard's extracted grep rather than invoking
# tests/run.sh. run.sh execs this whole directory once its guards pass, so
# calling it from here recurses — and terminates only while the guard still
# works. That shape passes for the wrong reason and hangs on the exact
# regression it is meant to catch.

load test_helper

SKILL_MD="${REPO_ROOT}/SKILL.md"
SYNTHESIS="${REPO_ROOT}/docs/synthesis.md"
ADVERSARY="${REPO_ROOT}/docs/adversary.md"
RUN_SH="${REPO_ROOT}/tests/run.sh"

# The matcher rule as SKILL.md must never spell it. Safe to keep here: the
# drift guard greps SKILL.md alone, not the tree.
MATCHER_LITERAL='token_overlap >= 0.6'

@test "split doc set exists" {
  local f
  for f in "$SKILL_MD" "$SYNTHESIS" "$ADVERSARY" "$RUN_SH"; do
    [[ -f "$f" ]] || {
      echo "expected file not found: $f"
      echo "  the SKILL.md/docs split contract spans all four files"
      return 1
    }
  done
}

@test "SKILL.md does not carry the matcher rule literal" {
  grep -qF "$MATCHER_LITERAL" "$SKILL_MD" && {
    echo "SKILL.md contains the matcher rule literal '${MATCHER_LITERAL}'"
    echo "  this rule belongs only in docs/synthesis.md; a second copy lets"
    echo "  the spec and the paraphrase drift apart"
    return 1
  }
  return 0
}

@test "docs/synthesis.md keeps its three section anchors" {
  local anchor
  for anchor in '## Matcher' '## Promotion paths' '## Demotion recording'; do
    grep -qxF "$anchor" "$SYNTHESIS" || {
      echo "docs/synthesis.md missing section anchor '${anchor}'"
      echo "  SKILL.md and docs/adversary.md deep-link to these headings;"
      echo "  renaming one breaks those links without any other signal"
      return 1
    }
  done
}

@test "docs/adversary.md links back to the synthesis anchors" {
  local found
  found=$(grep -cE 'synthesis\.md#(matcher|promotion-paths)' "$ADVERSARY")
  ((found >= 2)) || {
    echo "docs/adversary.md has ${found} synthesis anchor backlinks; expected >= 2"
    echo "  adversary mechanics defer to synthesis for the matcher and the"
    echo "  promotion paths rather than restating them"
    return 1
  }
}

@test "tests/run.sh still runs the matcher drift guard" {
  # Pin the guard by a fragment of its live regex. Matching the threshold
  # text instead would re-create the staleness this test was added to catch.
  grep -qE 'grep -qE .token_overlap\[\[:space:\]\]' "$RUN_SH" || {
    echo "tests/run.sh no longer contains the matcher drift-guard grep"
    echo "  without it, a matcher rule copied into SKILL.md ships unnoticed."
    echo "  if the guard was intentionally retuned, update this pin to a"
    echo "  fragment of the new pattern — do not delete the check"
    return 1
  }
}

@test "the matcher drift guard actually fires on a violation" {
  # Liveness: the guard's presence is not proof it works. Plant the literal
  # in a copied SKILL.md and run the guard's own grep against it.
  #
  # This re-runs the extracted guard line rather than invoking tests/run.sh,
  # which execs the whole tests/bats directory (this file included) once the
  # guard passes. Shelling out to run.sh here recurses, and it only terminates
  # while the guard is working — so it would hang on exactly the regression
  # this test exists to catch.
  local planted="${BATS_TEST_TMPDIR}/SKILL.md"
  cp "$SKILL_MD" "$planted"
  printf '\n%s\n' "$MATCHER_LITERAL" >>"$planted"

  local guard
  guard=$(grep -oE "grep -qE '[^']+'" "$RUN_SH" | head -1)
  [[ -n "$guard" ]] || {
    echo "could not extract the drift-guard grep from tests/run.sh"
    echo "  the pin in the previous test matched but the extraction anchor"
    echo "  did not — realign both before trusting this check"
    return 1
  }

  run bash -c "${guard} \"\$1\"" _ "$planted"
  [[ "$status" -eq 0 ]] || {
    echo "planted the matcher literal in SKILL.md; the guard's grep did not match it"
    echo "  extracted guard: ${guard}"
    echo "  the guard is present but would not reject a real violation"
    return 1
  }
}
