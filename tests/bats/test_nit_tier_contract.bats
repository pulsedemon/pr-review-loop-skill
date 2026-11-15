#!/usr/bin/env bats

# The `nit` severity is legal in both schemas and partitioned into `nits[]`, but
# it stayed emitted-by-nobody and rendered-nowhere for its whole life. Two
# halves have to hold together or it lapses back:
#
#   1. at least one persona tells the model when to pick `nit`, and says how it
#      differs from `out_of_scope` (both are "not a blocker", and without the
#      distinction the model has no rule for choosing);
#   2. both summary templates render a nits section. `promote_findings.py`
#      routes nits to `nits[]` and `pr_loop_state.py` counts them, so an emitted
#      nit that no template renders is counted and then silently dropped.
#
# Deleting either half leaves the other passing and the tier useless, so each is
# pinned separately. the emitting personas are `tests` and `comments`.
# the comments exclusion keeps misstated behavior out of the nit tier.
#
# Mutation-tested before requesting review (2026-08-21 round):
#   - delete the `## What to flag as `nit`` section from tests.md -> the tests.md
#     test fails on the section anchor, not vacuously. same for comments.md.
#   - delete the nits block from summary_ready.md -> only the ready-template
#     test fails; needs_attention stays green.
#   - drop the out_of_scope contrast sentence from comments.md while keeping the
#     heading -> the distinction test fails while the presence test passes.
#     that is the mutation a presence-only grep would miss. a first draft
#     grepped the section for the bare token out_of_scope and stayed green
#     under this mutation: the comments ownership sentence also says
#     out_of_scope. the assertion now anchors on the contrast phrase itself.
#   - drop nits from either "Render verbatim, substituting ..." line in
#     docs/step5-summary.md -> the step5 test fails. the templates carry the
#     placeholder; that doc carries the instruction to fill it.
#   - delete one or both of those lines outright -> the step5 test fails on the
#     count. an earlier draft looped over the grep matches with no count guard,
#     so deleting both ran the body zero times and passed vacuously.
#   - delete either persona's ownership/carve-out wording -> the overlap test
#     fails, per persona. whole-word anchored (`exceptions?|owns`) because a
#     loose alternation once matched "own" inside unrelated prose.
#   - delete the claim-must-remain-true sentence from comments.md -> the
#     exclusion test fails while every other comments test passes.
#   - delete every criterion bullet from both personas -> the two enumeration
#     tests fail. verified that before they existed the whole 6-test file
#     stayed green under exactly that mutation: the presence and ownership
#     checks match the introductory prose, so the tier could regress to an
#     empty rule with its own contract test passing.
#   - drop the other-blockers carve-out, the mutation carve-out, or the
#     nonexistent-branch rule from tests.md -> the safeguard test fails.
#     those three sentences are what keep the tier off findings labeled
#     loop_true_positive and off factually wrong ones.
#   - the tier's central promotion property (multi-source nit stays a nit) is
#     pinned in test_promote_findings.bats, not here.

load test_helper

# Extract one persona section by its exact `## <heading>` line, stopping at the
# next `##`. A whole-file grep cannot tell a nit rule from a passing mention of
# the word "nit" in a Rules bullet or an out_of_scope list. exit, not
# capturing=0, at the section end: resuming on a duplicated heading would union
# the sections, letting a stray duplicate satisfy wording the real one lost.
_persona_section() {
  local file="$1" heading="$2"
  awk -v want="## $heading" '
    $0 == want { capturing = 1; next }
    capturing && /^## / { exit }
    capturing { print }
  ' "${REPO_ROOT}/reviewers/${file}"
}

# Count the `- ` criterion bullets in a section. The presence tests below pass
# on heading + prose alone, so without a bullet floor the whole tier can be
# gutted to an empty rule the model can never apply while the suite stays green.
_nit_bullets() {
  _persona_section "$1" 'What to flag as `nit`' | grep -c '^- ' || true
}

_assert_nit_section() {
  local file="$1"
  local body
  body=$(_persona_section "$file" 'What to flag as `nit`')

  [[ -n "$body" ]] || {
    echo "reviewers/${file} has no '## What to flag as \`nit\`' section"
    echo "  the persona no longer tells the model when to pick nit, so the"
    echo "    tier goes back to being emitted by nobody"
    return 1
  }
  grep -q 'differs from `out_of_scope`' <<<"$body" || {
    echo "reviewers/${file} nit section never contrasts nit with out_of_scope"
    echo "  both are 'not a blocker'; without the distinction the model has"
    echo "    no rule for choosing between them"
    return 1
  }
}

@test "reviewers/tests.md defines when to emit a nit" {
  _assert_nit_section tests.md
}

@test "reviewers/comments.md defines when to emit a nit" {
  _assert_nit_section comments.md
}

@test "nit sections say which rule wins where two severities could match" {
  local file body
  for file in tests.md comments.md; do
    body=$(_persona_section "$file" 'What to flag as `nit`')
    grep -qwE 'exceptions?|owns' <<<"$body" || {
      echo "reviewers/${file} nit section has no ownership wording"
      echo "  without a stated carve-out the same finding matches a"
      echo "    blocker/suggestion rule and the nit rule at once"
      return 1
    }
  done
}

@test "comments.md nit tier requires the underlying claim to stay true" {
  # a reference that misstates behavior remains a correctness finding.
  local body
  body=$(_persona_section comments.md 'What to flag as `nit`')
  grep -q 'must remain true' <<<"$body" || {
    echo "reviewers/comments.md nit section lost its exclusion sentence"
    echo "  without 'the claim itself must remain true' the stale-reference"
    echo "    nit reaches misstated-behavior findings the tier must not touch"
    return 1
  }
}

@test "tests.md nit tier enumerates its concrete cases" {
  # the five evidence-backed shapes. anchored on a distinct phrase per bullet so
  # deleting one fails here rather than leaving an unappliable rule behind.
  local body
  body=$(_persona_section tests.md 'What to flag as `nit`')
  local pattern
  for pattern in 'log or status message' 'Cosmetic output formatting' 'fails loudly' 'Field-completeness' 'nothing reaches'; do
    grep -qi -- "$pattern" <<<"$body" || {
      echo "reviewers/tests.md nit section lost its '${pattern}' case"
      echo "  the tier is closed to the enumerated list, so a dropped case"
      echo "    silently narrows it to nothing the model can apply"
      return 1
    }
  done
  [[ "$(_nit_bullets tests.md)" -ge 4 ]] || {
    echo "reviewers/tests.md nit section has fewer than 4 criterion bullets"
    return 1
  }
}

@test "comments.md nit tier enumerates its concrete cases" {
  local body
  body=$(_persona_section comments.md 'What to flag as `nit`')
  local pattern
  for pattern in 'line-number or line-range reference' 'wording imprecision'; do
    grep -qi -- "$pattern" <<<"$body" || {
      echo "reviewers/comments.md nit section lost its '${pattern}' case"
      return 1
    }
  done
  [[ "$(_nit_bullets comments.md)" -ge 2 ]] || {
    echo "reviewers/comments.md nit section has fewer than 2 criterion bullets"
    return 1
  }
}

@test "tests.md keeps ineffective-test findings out of the nit tier" {
  # the mutation carve-out and the nonexistent-branch rule are what stop the
  # tier reaching Move A/A.1 vacuity findings (loop_true_positive in the
  # corpus) and factually-wrong test requests.
  local body
  body=$(_persona_section tests.md 'What to flag as `nit`')
  # the sentence wraps, so match a fragment that lives on one line
  grep -q 'still passes when the behavior it names' <<<"$body" || {
    echo "reviewers/tests.md nit section lost the mutation carve-out"
    echo "  without it the tier demotes tests that pass for the wrong reason"
    return 1
  }
  grep -q 'They do not override the other blockers' <<<"$body" || {
    echo "reviewers/tests.md nit section lost the other-blockers carve-out"
    echo "  a cosmetic gap inside a bug fix matches both a nit bullet and"
    echo "    the regression-test blocker, so the persona assigns two"
    echo "    severities to one finding"
    return 1
  }
  grep -q 'belongs in no severity' <<<"$body" || {
    echo "reviewers/tests.md nit section lost the nonexistent-branch rule"
    echo "  a test request on a branch that does not exist is wrong on the"
    echo "    facts, not trivial; without this it lands as a nit"
    return 1
  }
}

@test "step5 contract tells the host to render nits, not just the templates" {
  local matches
  matches=$(grep -c 'Render verbatim, substituting' "${REPO_ROOT}/docs/step5-summary.md")
  [[ "$matches" -eq 2 ]] || {
    echo "expected exactly 2 'Render verbatim, substituting' lines in"
    echo "docs/step5-summary.md, found ${matches}"
    echo "  the count guard exists so deleting a contract line cannot pass"
    echo "    vacuously"
    return 1
  }
  local line
  while IFS= read -r line; do
    grep -q 'nit' <<<"$line" || {
      echo "a step5 substitution line does not mention nits:"
      echo "  ${line}"
      echo "  the templates carry the placeholder; this doc carries the"
      echo "    instruction to fill it"
      return 1
    }
  done < <(grep 'Render verbatim, substituting' "${REPO_ROOT}/docs/step5-summary.md")
}

@test "both summary templates render a nits section" {
  local tpl
  for tpl in summary_ready.md summary_needs_attention.md; do
    grep -qi '^\*\*Nits' "${REPO_ROOT}/templates/${tpl}" || {
      echo "templates/${tpl} has no nits block"
      echo "  an emitted nit is partitioned and counted in n_nits, then"
      echo "    silently dropped from the posted summary"
      return 1
    }
  done
}
