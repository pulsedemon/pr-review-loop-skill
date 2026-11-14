#!/usr/bin/env bats

# The yagni, requirements, and blind_spots applicability gates are
# load-bearing: when they fire they early-exit with verdict:approve and
# suppress ALL findings for that persona. The structurally identical
# type_design gate is pinned by test_type_design_gate_text.bats for the
# same reason; these gates need the same protection so a stray edit can't
# silently delete the gate language, reopen a recall gap, or restate the
# §4d routing condition incorrectly while the suite stays green.
#
# blind_spots is the odd one out twice over. It has no '## Applicability
# gate' heading, so the structural grep used for the other two does not
# apply to it. And it was the one gated persona carrying procedure moves
# whose gate did not carve them out: requirements has the same shape and
# has carved Move C out all along. Without the carve-out the prompt
# instructs two different outputs on one diff (#121).

load test_helper

@test "yagni.md keeps the applicability gate early-exit" {
  grep -qE '^## Applicability gate' "${REPO_ROOT}/reviewers/yagni.md" || {
    echo "yagni.md no longer has an '## Applicability gate' section"
    return 1
  }
  grep -q '"reviewer":"yagni","verdict":"approve"' "${REPO_ROOT}/reviewers/yagni.md" || {
    echo "yagni.md gate no longer shows the verdict:approve early-exit example"
    return 1
  }
  # Pin the trigger polarity, not just presence. The gate early-exits when
  # the diff adds *none* of the recognized surfaces. An edit flipping "none"
  # to "any" inverts the gate so it early-exits exactly when a surface IS
  # present (silently approving the PRs the persona exists to catch); the
  # presence greps above would still pass. Same direction-pinning rationale
  # as test_type_design_gate_text.bats.
  grep -q 'adds or modifies none of these' "${REPO_ROOT}/reviewers/yagni.md" || {
    echo "yagni.md gate no longer states the 'none of these' early-exit polarity"
    echo "  — a none->any inversion would early-exit when a surface is present and stay green"
    return 1
  }
}

@test "yagni.md gate recognizes premature-optimization constructs (suggestion-path recall)" {
  # Without this surface a cache/memoization/pool/lazy-init added inside an
  # existing body matches no recognized surface, so the gate early-exits
  # and silently drops the premature-optimization suggestion. Pin the
  # surface so the suggestion path stays reachable.
  grep -q 'cache, memoization wrapper, object pool, or lazy-initialization construct' \
    "${REPO_ROOT}/reviewers/yagni.md" || {
    echo "yagni.md gate no longer lists the premature-optimization surface"
    echo "  — the gate can again early-exit past the 'premature optimization' suggestion"
    return 1
  }
}

@test "requirements.md keeps the applicability gate early-exit and both conjuncts" {
  grep -qE '^## Applicability gate' "${REPO_ROOT}/reviewers/requirements.md" || {
    echo "requirements.md no longer has an '## Applicability gate' section"
    return 1
  }
  grep -q '"reviewer":"requirements","verdict":"approve"' "${REPO_ROOT}/reviewers/requirements.md" || {
    echo "requirements.md gate no longer shows the verdict:approve early-exit example"
    return 1
  }
  # Both conjuncts must survive: no stated requirement / no resolvable
  # ticket content, AND Move C does not apply. Dropping either widens the
  # approve path past the persona's blocker duty.
  grep -qi 'no linked-ticket content is available' "${REPO_ROOT}/reviewers/requirements.md" || {
    echo "requirements.md gate no longer pins the 'no requirement / no ticket content' conjunct"
    return 1
  }
  grep -q 'Move C below does not apply' "${REPO_ROOT}/reviewers/requirements.md" || {
    echo "requirements.md gate no longer pins the 'Move C does not apply' conjunct"
    return 1
  }
  # Pin the conjunction polarity, not just the conjunct contents. The gate
  # early-exits only when BOTH conjuncts hold. An edit flipping "both ...
  # hold" to "either ... holds" widens the approve path to fire on one
  # conjunct (e.g. no requirement but Move C does apply), dropping the
  # cross-doc-consistency blocker duty; the conjunct greps above survive it.
  grep -qE 'both\*{0,2} of the following hold' "${REPO_ROOT}/reviewers/requirements.md" || {
    echo "requirements.md gate no longer states the 'both ... hold' conjunction polarity"
    echo "  — a both->either flip would early-exit on a single conjunct and stay green"
    return 1
  }
}

@test "blind_spots.md carves Move A and Move C out of its early exit" {
  # blind_spots has no '## Applicability gate' heading; its gate is the
  # early-exit prose at the top (:5) and its restatement in '## Rules'.
  # Both halves are pinned: an edit that fixes one and not the other
  # leaves the #121 contradiction standing in the survivor.
  local f="${REPO_ROOT}/reviewers/blind_spots.md"
  # A missing file already fails the first grep below, but blames the
  # carve-out and leaks grep's stderr. Name the real cause instead: the
  # trailing negative assertion would also read ENOENT as "pattern absent".
  [[ -f "$f" ]] || {
    echo "reviewers/blind_spots.md does not exist"
    return 1
  }

  # Whole clause from `none` through the moves. Starting the match later
  # lets `none`->`any` or `and`->`or` invert the gate and stay green, and
  # either flip early-exits on the diffs this persona exists to review.
  grep -q 'has none of the patterns listed below and neither Move A nor Move C applies' "$f" || {
    echo "blind_spots.md:5 early exit clause changed"
    echo "  pins polarity ('none') and conjunction ('and'), not just the moves"
    return 1
  }
  # The Rules restatement carries the same polarity independently.
  grep -q '1. None of (a)/(b)/(c) is reachable in the diff.' "$f" || {
    echo "blind_spots.md '## Rules' conjunct 1 no longer reads 'None of (a)/(b)/(c)'"
    echo "  'Any' there early-exits on category-bearing diffs"
    return 1
  }
  # Per-move, so swapping one move for another fails rather than passing
  # on the bare word "Move".
  grep -q 'Move A above does not apply' "$f" || {
    echo "blind_spots.md '## Rules' dropped the Move A conjunct"
    echo "  — Move A is mandatory for every test in the diff and raises blockers"
    return 1
  }
  grep -q 'Move C above does not apply' "$f" || {
    echo "blind_spots.md '## Rules' dropped the Move C conjunct"
    echo "  — Move C is mandatory on doc+spec diffs and raises blockers"
    return 1
  }
  # Conjunction polarity, same rationale as the requirements pin above.
  # 'all' not 'both': blind_spots carves out two moves, requirements one.
  grep -qE 'all\*{0,2} of the following hold' "$f" || {
    echo "blind_spots.md gate no longer states the 'all ... hold' conjunction polarity"
    echo "  — an all->any flip would early-exit on a single conjunct and stay green"
    return 1
  }
  # Negative: the four greps above only prove the carve-out is present.
  # A regression that keeps it AND re-adds the flat pre-#121 sentence
  # restores the contradiction with every positive assertion still green.
  if grep -qE '\(c\) is reachable in the diff, return' "$f"; then
    echo "blind_spots.md re-added the unconditional 'none of (a)/(b)/(c) -> approve' early exit"
    echo "  — that is the #121 contradiction: Move A and Move C raise blockers on those diffs"
    return 1
  fi
}

@test "gate files pin the §4d cap conjunct on the shallow-flag line" {
  # The shallow-flag rationale paraphrases SKILL.md §4d. §4d forces the
  # adversary pass only while shallow_adversary_runs is below its cap;
  # dropping that conjunct overstates the routing as unconditional. Assert
  # every gate file keeps 'forces an adversary pass' and 'below its cap'
  # on the same line so the paraphrase can't drift back.
  local f
  for f in yagni requirements type_design; do
    grep -E 'forces an adversary pass while .*below its cap' \
      "${REPO_ROOT}/reviewers/${f}.md" >/dev/null || {
      echo "reviewers/${f}.md shallow-flag line dropped the 'below its cap' (§4d) conjunct"
      return 1
    }
  done
}
